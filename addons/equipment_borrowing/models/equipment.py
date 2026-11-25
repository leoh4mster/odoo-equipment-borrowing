from odoo import fields, models


class Equipment(models.Model):
    _name = "equipment.borrowing.equipment"
    _description = "Borrowable Equipment"
    _order = "code, id"

    name = fields.Char(string="Equipment Name", required=True)
    code = fields.Char(string="Equipment Code", required=True, copy=False)
    category = fields.Selection(
        selection=[
            ("laptop", "Laptop"),
            ("projector", "Projector"),
            ("camera", "Camera"),
            ("meeting", "Meeting Equipment"),
            ("other", "Other"),
        ],
        required=True,
        default="other",
    )
    description = fields.Text()
    active = fields.Boolean(default=True)
    request_ids = fields.One2many(
        "equipment.borrowing.request",
        "equipment_id",
        string="Borrow Requests",
        readonly=True,
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "The equipment code must be unique.",
    )
