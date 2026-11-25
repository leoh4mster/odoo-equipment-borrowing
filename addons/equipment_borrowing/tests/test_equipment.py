from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestEquipment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee, cls.manager = cls.env["res.users"].with_context(
            no_reset_password=True,
        ).create([
            {
                "name": "Equipment Test Employee",
                "login": "equipment_test_employee",
                "group_ids": [Command.set([cls.env.ref("base.group_user").id])],
            },
            {
                "name": "Equipment Test Manager",
                "login": "equipment_test_manager",
                "group_ids": [Command.set([
                    cls.env.ref("equipment_borrowing.group_equipment_manager").id,
                ])],
            },
        ])
        cls.Equipment = cls.env["equipment.borrowing.equipment"].with_user(cls.manager)
        cls.equipment = cls.Equipment.create({
            "name": "Shared projector",
            "code": "TEST-EQ-001",
            "category": "projector",
        })

    def test_manager_can_create_and_update(self):
        self.assertFalse(self.Equipment.env.user.has_group("base.group_system"))
        equipment = self.Equipment.create({"name": "Office laptop", "code": "TEST-EQ-002"})
        self.assertTrue(equipment.active)
        self.assertEqual(equipment.category, "other")
        equipment.write({"description": "Stored in meeting room A"})
        equipment.invalidate_recordset(["description"])
        self.assertEqual(equipment.description, "Stored in meeting room A")

    @mute_logger("odoo.sql_db")
    def test_code_is_unique_on_create(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.Equipment.create({"name": "Another projector", "code": self.equipment.code})

    @mute_logger("odoo.sql_db")
    def test_code_is_unique_on_write(self):
        equipment = self.Equipment.create({"name": "Camera", "code": "TEST-EQ-002"})
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            equipment.write({"code": self.equipment.code})

    @mute_logger("odoo.sql_db")
    def test_code_is_required(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.Equipment.create({"name": "Equipment without a code"})

    @mute_logger("odoo.sql_db")
    def test_name_is_required(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.Equipment.create({"code": "TEST-EQ-002"})

    @mute_logger("odoo.sql_db")
    def test_archive_keeps_record_and_code_reserved(self):
        self.equipment.active = False
        self.assertTrue(self.equipment.exists())
        self.assertNotIn(self.equipment, self.Equipment.search([]))
        self.assertIn(self.equipment, self.Equipment.with_context(active_test=False).search([]))
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.Equipment.create({"name": "Reused code", "code": self.equipment.code})
        self.equipment.active = True
        self.assertIn(self.equipment, self.Equipment.search([]))

    def test_employee_is_read_only(self):
        equipment = self.equipment.with_user(self.employee)
        self.assertEqual(equipment.read(["code"])[0]["code"], "TEST-EQ-001")
        with self.assertRaises(AccessError):
            equipment.write({"name": "Unauthorized change"})
        with self.assertRaises(AccessError):
            self.Equipment.with_user(self.employee).create({"name": "Unauthorized item", "code": "TEST-EQ-002"})

    def test_public_cannot_read(self):
        public_user = self.env.ref("base.public_user")
        with self.assertRaises(AccessError):
            self.equipment.with_user(public_user).read(["name"])

    def test_manager_cannot_delete(self):
        with self.assertRaises(AccessError):
            self.equipment.unlink()
