from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import mute_logger

from .common import BorrowRequestCase


class TestBorrowRequest(BorrowRequestCase):
    def test_defaults_and_unique_numbers(self):
        values = {"equipment_id": self.equipment.id, "reason": "Same-day meeting"}
        first, second = self.Request.create([values, values])
        self.assertEqual(first.applicant_id, self.employee_a)
        self.assertEqual(first.state, "draft")
        self.assertEqual(first.borrow_date, fields.Date.context_today(self.Request))
        self.assertEqual(first.borrow_date, first.return_date)
        self.assertTrue(first.name.startswith("EBR/"))
        self.assertNotEqual(first.name, second.name)

    def test_context_cannot_forge_identity_state_or_number(self):
        request = self.Request.with_context(
            default_applicant_id=self.employee_b.id,
            default_state="approved",
            default_name="FORGED-NUMBER",
        ).create({**self.values, "name": "FORGED-NUMBER"})
        self.assertEqual(request.applicant_id, self.employee_a)
        self.assertEqual(request.state, "draft")
        self.assertNotEqual(request.name, "FORGED-NUMBER")

    def test_cannot_create_for_another_applicant(self):
        for user in (self.employee_a, self.manager):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.Request.with_user(user).create({**self.values, "applicant_id": self.employee_b.id})

    def test_cannot_create_in_another_state(self):
        with self.assertRaises(AccessError):
            self.Request.create({**self.values, "state": "approved"})

    def test_identity_and_state_cannot_be_written(self):
        for user in (self.employee_a, self.manager):
            for values in ({"name": "FORGED"}, {"applicant_id": self.employee_b.id}, {"state": "approved"}):
                with self.subTest(user=user.login, values=values), self.assertRaises(AccessError):
                    self.request_a.with_user(user).write(values)

    def test_employee_only_sees_and_edits_own_requests(self):
        visible = self.Request.search([])
        self.assertIn(self.request_a, visible)
        self.assertNotIn(self.request_b, visible)
        self.assertNotIn(self.request_manager, visible)
        with self.assertRaises(AccessError):
            self.request_b.with_user(self.employee_a).read(["reason"])
        with self.assertRaises(AccessError):
            self.request_b.with_user(self.employee_a).write({"reason": "Unauthorized"})
        self.request_a.write({"reason": "Updated presentation"})
        self.assertEqual(self.request_a.reason, "Updated presentation")

    def test_manager_can_access_all_drafts(self):
        requests = self.Request.with_user(self.manager).search([])
        for request in (self.request_a, self.request_b, self.request_manager):
            self.assertIn(request, requests)
        self.request_b.with_user(self.manager).write({"reason": "Clarified by equipment manager"})
        self.assertEqual(self.request_b.with_user(self.manager).reason, "Clarified by equipment manager")

    def test_invalid_dates_rejected_on_create(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Request.create({**self.values, "return_date": "2026-11-30"})

    def test_invalid_dates_rejected_on_write(self):
        original_date = self.request_a.return_date
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.request_a.write({"return_date": "2026-11-30"})
        self.assertEqual(self.request_a.return_date, original_date)

    def test_same_day_borrow_is_allowed(self):
        request = self.Request.create({**self.values, "return_date": self.values["borrow_date"]})
        self.assertEqual(request.borrow_date, request.return_date)

    def test_archived_equipment_rejected_on_create(self):
        self.other_equipment.active = False
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Request.create({**self.values, "equipment_id": self.other_equipment.id})

    def test_context_defaults_still_validate_equipment_and_dates(self):
        self.other_equipment.active = False
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Request.with_context(default_equipment_id=self.other_equipment.id).create({"reason": "Archived default"})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Request.with_context(default_borrow_date="2026-12-05", default_return_date="2026-12-01").create({
                "equipment_id": self.equipment.id, "reason": "Invalid default dates",
            })

    def test_cannot_change_to_archived_equipment(self):
        self.other_equipment.active = False
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.request_a.write({"equipment_id": self.other_equipment.id})
        self.assertEqual(self.request_a.equipment_id, self.equipment)

    def test_archiving_equipment_preserves_existing_request(self):
        self.equipment.active = False
        self.assertEqual(self.request_a.read(["equipment_id"])[0]["equipment_id"][0], self.equipment.id)
        self.request_a.write({"reason": "Existing historical draft"})
        self.assertTrue(self.request_a.exists())

    def test_equipment_back_reference_respects_record_rules(self):
        expected_by_user = [
            (self.manager, {self.request_a.id, self.request_b.id, self.request_manager.id}),
            (self.employee_a, {self.request_a.id}),
            (self.employee_b, {self.request_b.id}),
        ]
        for user, expected_ids in expected_by_user:
            with self.subTest(user=user.login):
                # with_user shares this test transaction's relation cache.
                # Fresh browser requests do not share that cache, so clear it
                # before checking each user's record-rule-filtered query.
                self.equipment.invalidate_recordset(["request_ids"])
                equipment = self.equipment.with_user(user)
                self.assertEqual(set(equipment.request_ids.ids), expected_ids)
                self.assertEqual(set(equipment.read(["request_ids"])[0]["request_ids"]), expected_ids)

    def test_public_cannot_read_or_create(self):
        public_user = self.env.ref("base.public_user")
        with self.assertRaises(AccessError):
            self.request_a.with_user(public_user).read(["name"])
        with self.assertRaises(AccessError):
            self.Request.with_user(public_user).create(self.values)

    def test_requests_cannot_be_deleted(self):
        for user in (self.employee_a, self.manager):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.request_a.with_user(user).unlink()

    def test_copy_gets_current_applicant_and_new_number(self):
        copy = self.request_a.with_user(self.manager).copy()
        self.assertEqual(copy.applicant_id, self.manager)
        self.assertEqual(copy.state, "draft")
        self.assertNotEqual(copy.name, self.request_a.name)

    @mute_logger("odoo.sql_db")
    def test_equipment_is_required(self):
        values = {key: value for key, value in self.values.items() if key != "equipment_id"}
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.Request.create(values)
