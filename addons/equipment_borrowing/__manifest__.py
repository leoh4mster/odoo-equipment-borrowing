{
    "name": "Equipment Borrowing",
    "summary": "Internal equipment borrowing and approval management",
    "version": "19.0.1.5.0",
    "category": "Productivity",
    "author": "Lehan Zhou",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/equipment_security.xml",
        "security/ir.model.access.csv",
        "data/borrow_request_sequence.xml",
        "views/borrow_request_views.xml",
        "views/equipment_views.xml",
        "views/equipment_menus.xml",
    ],
    "application": True,
    "installable": True,
}
