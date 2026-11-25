from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import mute_logger

from .common import BorrowRequestCase


class TestBorrowWorkflow(BorrowRequestCase):
    def setUp(self):
        super().setUp()
        self._equipment_counter = 0

    def _request_in_state(self, state):
        self._equipment_counter += 1
        equipment = self.env["equipment.borrowing.equipment"].with_user(self.manager).create({
            "name": "Workflow equipment",
            "code": f"WORKFLOW-TEST-{self._equipment_counter:03d}",
        })
        request = self.Request.create({**self.values, "equipment_id": equipment.id})
        if state != "draft":
            request.action_submit()
            manager_request = request.with_user(self.manager)
            if state == "rejected":
                manager_request.action_reject()
            elif state in ("approved", "borrowed", "returned"):
                manager_request.action_approve()
                if state in ("borrowed", "returned"):
                    manager_request.action_borrow()
                if state == "returned":
                    manager_request.action_return()
        self.assertEqual(request.state, state)
        return request

    def test_complete_flow_and_release(self):
        self.request_a.action_submit()
        self.assertEqual(self.request_a.state, "pending")
        manager_request = self.request_a.with_user(self.manager)
        manager_request.action_approve()
        self.assertEqual(manager_request.state, "approved")
        manager_request.action_borrow()
        self.assertEqual(manager_request.state, "borrowed")
        manager_request.action_return()
        self.assertEqual(manager_request.state, "returned")
        self.request_b.action_submit()
        self.request_b.with_user(self.manager).action_approve()
        self.assertEqual(self.request_b.state, "approved")

    def test_rejection_does_not_reserve_equipment(self):
        self.request_a.action_submit()
        self.request_a.with_user(self.manager).action_reject()
        self.assertEqual(self.request_a.state, "rejected")
        self.request_b.action_submit()
        self.request_b.with_user(self.manager).action_approve()
        self.assertEqual(self.request_b.state, "approved")

    def test_all_invalid_state_transitions(self):
        required_state = {
            "action_submit": "draft", "action_approve": "pending",
            "action_reject": "pending", "action_borrow": "approved",
            "action_return": "borrowed",
        }
        for state in ("draft", "pending", "approved", "rejected", "borrowed", "returned"):
            request = self._request_in_state(state)
            for method, required in required_state.items():
                if required == state:
                    continue
                actor = self.employee_a if method == "action_submit" else self.manager
                with self.subTest(state=state, method=method), self.assertRaises(UserError):
                    getattr(request.with_user(actor), method)()
                self.assertEqual(request.state, state)

    def test_employee_cannot_perform_manager_actions(self):
        for method, state in (
            ("action_approve", "pending"), ("action_reject", "pending"),
            ("action_borrow", "approved"), ("action_return", "borrowed"),
        ):
            request = self._request_in_state(state)
            with self.subTest(method=method), self.assertRaises(AccessError):
                getattr(request, method)()
            self.assertEqual(request.state, state)

    def test_only_applicant_can_submit(self):
        for actor in (self.employee_b, self.manager):
            with self.subTest(actor=actor.login), self.assertRaises(AccessError):
                self.request_a.with_user(actor).action_submit()
        self.assertEqual(self.request_a.state, "draft")

    def test_submitted_requests_are_frozen_for_all_roles(self):
        changes = (
            {"reason": "Changed after submission"},
            {"equipment_id": self.other_equipment.id},
            {"borrow_date": "2026-12-02"},
            {"return_date": "2026-12-04"},
        )
        for state in ("pending", "approved", "rejected", "borrowed", "returned"):
            request = self._request_in_state(state)
            for actor in (self.employee_a, self.manager):
                for values in changes:
                    with self.subTest(state=state, actor=actor.login, values=values), self.assertRaises(UserError):
                        request.with_user(actor).write(values)
            self.assertEqual(request.state, state)

    def test_context_cannot_bypass_state_protection(self):
        request = self._request_in_state("approved")
        for actor in (self.employee_a, self.manager):
            with self.subTest(actor=actor.login), self.assertRaises(AccessError):
                request.with_user(actor).with_context(
                    skip_workflow=True, allow_state_write=True, skip_access_check=True,
                ).write({"state": "returned"})
        self.assertEqual(request.state, "approved")

    def test_two_pending_requests_can_coexist_but_only_one_can_be_approved(self):
        self.request_a.action_submit()
        self.request_b.action_submit()
        self.request_a.with_user(self.manager).action_approve()
        with self.assertRaises(ValidationError):
            self.request_b.with_user(self.manager).action_approve()
        self.assertEqual(self.request_b.state, "pending")

    def test_borrowed_equipment_blocks_another_approval(self):
        self.request_a.action_submit()
        self.request_a.with_user(self.manager).action_approve()
        self.request_a.with_user(self.manager).action_borrow()
        self.request_b.action_submit()
        with self.assertRaises(ValidationError):
            self.request_b.with_user(self.manager).action_approve()
        self.assertEqual(self.request_b.state, "pending")

    @mute_logger("odoo.sql_db")
    def test_database_index_guards_both_active_states(self):
        for state in ("approved", "borrowed"):
            request = self._request_in_state(state)
            other = self.Request.create({**self.values, "equipment_id": request.equipment_id.id})
            other.action_submit()
            # Bypass the Python pre-check deliberately to test the final DB guard.
            with self.subTest(state=state), self.assertRaises(IntegrityError), self.cr.savepoint():
                self.env.cr.execute(
                    "UPDATE equipment_borrowing_request SET state = %s WHERE id = %s",
                    ["approved", other.id],
                )
            self.assertEqual(other.state, "pending")

    def test_archived_equipment_cannot_be_submitted(self):
        self.equipment.active = False
        with self.assertRaises(ValidationError):
            self.request_a.action_submit()
        self.assertEqual(self.request_a.state, "draft")

    def test_archived_equipment_cannot_be_approved(self):
        request = self._request_in_state("pending")
        request.equipment_id.with_user(self.manager).active = False
        with self.assertRaises(ValidationError):
            request.with_user(self.manager).action_approve()
        self.assertEqual(request.state, "pending")

    def test_archived_equipment_cannot_be_handed_out(self):
        request = self._request_in_state("approved")
        request.equipment_id.with_user(self.manager).active = False
        with self.assertRaises(ValidationError):
            request.with_user(self.manager).action_borrow()
        self.assertEqual(request.state, "approved")

    def test_archived_equipment_can_still_be_returned(self):
        request = self._request_in_state("borrowed")
        request.equipment_id.with_user(self.manager).active = False
        request.with_user(self.manager).action_return()
        self.assertEqual(request.state, "returned")

    def test_copy_of_returned_request_starts_a_new_draft(self):
        request = self._request_in_state("returned")
        copy = request.copy()
        self.assertEqual(copy.state, "draft")
        self.assertNotEqual(copy.name, request.name)
        self.assertEqual(copy.applicant_id, self.employee_a)

    def test_manager_can_run_own_request_through_the_flow(self):
        request = self.request_manager
        request.action_submit()
        request.action_approve()
        request.action_borrow()
        request.action_return()
        self.assertEqual(request.state, "returned")
