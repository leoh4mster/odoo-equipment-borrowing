from odoo import api, fields, models, _
from odoo.exceptions import AccessError, LockError, UserError, ValidationError


class BorrowRequest(models.Model):
    _name = "equipment.borrowing.request"
    _description = "Equipment Borrow Request"
    _order = "id desc"

    name = fields.Char(
        string="Request Number", required=True, readonly=True, copy=False,
        default=lambda self: self.env._("New"),
    )
    equipment_id = fields.Many2one(
        "equipment.borrowing.equipment",
        string="Equipment",
        required=True,
        ondelete="restrict",
        index=True,
        domain=[("active", "=", True)],
    )
    applicant_id = fields.Many2one(
        "res.users",
        string="Applicant",
        required=True,
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
        default=lambda self: self.env.user,
    )
    borrow_date = fields.Date(string="Planned Borrow Date", required=True, default=fields.Date.context_today)
    return_date = fields.Date(string="Planned Return Date", required=True, default=fields.Date.context_today)
    reason = fields.Text(required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("borrowed", "Borrowed"),
            ("returned", "Returned"),
        ],
        required=True,
        readonly=True,
        copy=False,
        default="draft",
    )

    _name_unique = models.Constraint("UNIQUE(name)", "The request number must be unique.")
    _active_equipment_unique = models.UniqueIndex(
        "(equipment_id) WHERE state IN ('approved', 'borrowed')",
        "This equipment already has an approved or borrowed request.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        prepared_values = []
        for values in vals_list:
            values = dict(values)
            if values.get("applicant_id", self.env.uid) != self.env.uid:
                raise AccessError(_("You can only create requests for yourself."))
            if values.get("state", "draft") != "draft":
                raise AccessError(_("New requests must start in draft."))
            # Explicit values also prevent client-supplied context defaults
            # from overriding the authenticated applicant or initial state.
            values["applicant_id"] = self.env.uid
            values["state"] = "draft"
            values["name"] = self.env["ir.sequence"].next_by_code("equipment.borrowing.request")
            if not values["name"]:
                raise UserError(_("The borrow request sequence is not configured."))
            prepared_values.append(values)
        return super().create(prepared_values)

    def write(self, values):
        self.check_access("write")
        if {"name", "applicant_id", "state"}.intersection(values):
            raise AccessError(_("The request number, applicant and state cannot be edited directly."))
        self._lock_and_refresh()
        if values and any(request.state != "draft" for request in self):
            raise UserError(_("Only draft requests can be edited."))
        return super().write(values)

    def _lock_and_refresh(self):
        self.flush_recordset()
        try:
            self.lock_for_update(allow_referencing=True)
        except LockError as error:
            raise UserError(_("This request is being updated. Please try again.")) from error
        self.invalidate_recordset(flush=False)

    def _transition(self, expected_state, target_state, *, manager_required):
        self.ensure_one()
        self.check_access("write")
        if manager_required:
            if not self.env.user.has_group("equipment_borrowing.group_equipment_manager"):
                raise AccessError(_("Only equipment managers can perform this action."))
        elif self.applicant_id != self.env.user:
            raise AccessError(_("Only the applicant can submit this request."))

        self._lock_and_refresh()
        if self.state != expected_state:
            raise UserError(_("The request is no longer in the required state. Refresh the page and try again."))
        if target_state in ("pending", "approved", "borrowed"):
            self._check_dates()
            self._check_equipment_active()
        if target_state == "approved":
            occupied = self.search_count([
                ("equipment_id", "=", self.equipment_id.id),
                ("state", "in", ["approved", "borrowed"]),
                ("id", "!=", self.id),
            ], limit=1)
            if occupied:
                raise ValidationError(_("This equipment already has an approved or borrowed request."))

        # Private, validated transitions use the inherited ORM write. No
        # client-supplied context flag can bypass the public write safeguards.
        # The unique partial index is the final guard against concurrent approvals.
        return super().write({"state": target_state})

    def action_submit(self):
        return self._transition("draft", "pending", manager_required=False)

    def action_approve(self):
        return self._transition("pending", "approved", manager_required=True)

    def action_reject(self):
        return self._transition("pending", "rejected", manager_required=True)

    def action_borrow(self):
        return self._transition("approved", "borrowed", manager_required=True)

    def action_return(self):
        return self._transition("borrowed", "returned", manager_required=True)

    @api.constrains("borrow_date", "return_date")
    def _check_dates(self):
        for request in self:
            if request.borrow_date and request.return_date and request.borrow_date > request.return_date:
                raise ValidationError(_("The planned return date cannot be earlier than the borrow date."))

    @api.constrains("equipment_id")
    def _check_equipment_active(self):
        for request in self:
            if request.equipment_id and not request.equipment_id.active:
                raise ValidationError(_("This equipment is archived. Choose active equipment or ask an equipment manager to restore it."))
