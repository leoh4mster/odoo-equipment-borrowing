from odoo import Command
from odoo.tests import TransactionCase


class BorrowRequestCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        employee_group = cls.env.ref("base.group_user")
        manager_group = cls.env.ref("equipment_borrowing.group_equipment_manager")
        cls.employee_a, cls.employee_b, cls.manager = cls.env["res.users"].with_context(
            no_reset_password=True,
        ).create([
            {"name": "Borrow Employee A", "login": "borrow_employee_a", "group_ids": [Command.set(employee_group.ids)]},
            {"name": "Borrow Employee B", "login": "borrow_employee_b", "group_ids": [Command.set(employee_group.ids)]},
            {"name": "Borrow Manager", "login": "borrow_manager", "group_ids": [Command.set(manager_group.ids)]},
        ])
        cls.equipment, cls.other_equipment = cls.env["equipment.borrowing.equipment"].with_user(cls.manager).create([
            {"name": "Shared projector", "code": "BORROW-TEST-001", "category": "projector"},
            {"name": "Shared camera", "code": "BORROW-TEST-002", "category": "camera"},
        ])
        cls.Request = cls.env["equipment.borrowing.request"].with_user(cls.employee_a)
        cls.values = {
            "equipment_id": cls.equipment.id,
            "borrow_date": "2026-12-01",
            "return_date": "2026-12-03",
            "reason": "Team presentation",
        }
        cls.request_a = cls.Request.create(cls.values)
        cls.request_b = cls.Request.with_user(cls.employee_b).create(cls.values)
        cls.request_manager = cls.Request.with_user(cls.manager).create(cls.values)
