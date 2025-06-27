# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from datetime import date

RES_PARTNER = 'res.partner'
HIS_PATIENT = 'his.patient'
MATE_HEALTH_CHECK_CUSTOMER_TYPE = 'mate.health.check.customer.type'
MATE_HEALTH_CHECK_PACKAGE = 'mate.health.check.package'
MATE_HEALTH_CHECK_PACKAGE_LINE = 'mate.health.check.package.line'


class MateHealthCheckPatient(models.Model):
    _name = HIS_PATIENT
    _description = 'Health Check Patient'
    _inherits = {
        RES_PARTNER: 'partner_id',
    }

    partner_id = fields.Many2one(RES_PARTNER, ondelete='restrict', auto_join=True, string='Related Partner', help='Partner-related data of the Patient')
    team_partner_id = fields.Many2one(
        RES_PARTNER,
        string='Medical examination group',
        help='Medical examination group to which the patient belongs',
    )
    active = fields.Boolean(string="Active", default=True)
    name = fields.Char(string='Name', required=True, help='Name of the patient')
    patient_id_number = fields.Char(string='PID', required=True, help='Unique identifier for the patient')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ], string='Gender', required=True, help='Gender of the patient')
    date_of_birth = fields.Date(string='Birth Date', help='Date of birth of the patient')
    age = fields.Integer(string='Age', compute='_compute_age', store=True, help='Age of the patient in years')
    phone = fields.Char(string='Phone', help='Phone number of the patient')
    email = fields.Char(string='Email', help='Email address of the patient')
    address = fields.Text(string='Address', help='Physical address of the patient')
    insurance_code = fields.Char(string='Insurance Code', help='Insurance code of the patient')
    priority_level = fields.Many2one(
        MATE_HEALTH_CHECK_CUSTOMER_TYPE,
        string='Priority Levels',
        help='Priority levels assigned to the patient for health checks'
    )
    package_ids = fields.Many2many(
        MATE_HEALTH_CHECK_PACKAGE,
        'patient_package_rel',
        'patient_id',
        'package_id',
        string='Health Check Packages',
        help='Health check packages associated with the patient'
    )
    package_line_ids = fields.One2many(
        comodel_name=MATE_HEALTH_CHECK_PACKAGE_LINE,
        compute='_compute_package_line_ids',
        string='Package Lines',
        readonly=True
    )
    package_name = fields.Char(
        string='Package',
        compute='_compute_package_name',
        store=True,
        help='Name of the health check package associated with the patient'
    )

    @api.depends('package_ids')
    def _compute_package_name(self):
        for record in self:
            if record.package_ids:
                record.package_name = ', '.join(record.package_ids.mapped('name'))
            else:
                record.package_name = ''

    @api.depends('package_ids.package_line_ids')
    def _compute_package_line_ids(self):
        for rec in self:
            lines = rec.package_ids.mapped('package_line_ids')
            rec.package_line_ids = lines

    @api.depends('date_of_birth')
    def _compute_age(self):
        """Tính tuổi từ ngày sinh"""
        for patient in self:
            if patient.date_of_birth:
                today = date.today()
                born = patient.date_of_birth
                patient.age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
            else:
                patient.age = 0

    @api.onchange('patient_id_number')
    def _check_hospital_number(self):
        num_str = self.patient_id_number or ''
        if self.patient_id_number:
            if len(num_str) != 9 or not num_str.startswith('8') or not num_str.isdigit():
                raise ValidationError(_("Hospital number must start with 8 and must be 9 characters long."))

    def action_open_smart_queue_view(self):
        """Mở view từ module mate_smart_queue"""
        try:
            # Thử tìm action từ module con
            action = self.env.ref('mate_smart_queue.action_patient_list_main')
            return action.read()[0]
        except ValueError:
            # Nếu không tìm thấy (module con chưa cài), dùng view mặc định
            return {
                'type': 'ir.actions.act_window',
                'name': 'Patient List',
                'res_model': HIS_PATIENT,
                'view_mode': 'list,form',
                'target': 'current',
            }

    def action_open_queue_list_view(self):
        """Mở view từ module mate_smart_queue"""
        try:
            # Thử tìm action từ module con
            action = self.env.ref('mate_smart_queue.action_queue_token')
            return action.read()[0]
        except ValueError:
            # Nếu không tìm thấy (module con chưa cài), dùng view mặc định
            return {
                'type': 'ir.actions.act_window',
                'name': 'Queue List',
                'res_model': HIS_PATIENT,
                'view_mode': 'list,form',
                'target': 'current',
            }
