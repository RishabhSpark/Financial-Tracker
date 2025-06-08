from sqlalchemy import Table, Column, String, Float, Integer, MetaData, ForeignKey

metadata = MetaData()

purchase_orders = Table(
    'purchase_orders', metadata,
    Column('po_id', String, primary_key=True),
    Column('client_name', String),
    Column('amount', Float),
    Column('status', String),
    Column('payment_terms', Integer),
    Column('payment_type', String),
    Column('start_date', String),
    Column('end_date', String),
    Column('duration_months', Integer),
    Column('payment_frequency', Integer, nullable=True),
)

milestones = Table(
    'milestones', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('po_id', String, ForeignKey('purchase_orders.po_id')),
    Column('milestone_name', String),
    Column('milestone_description', String),
    Column('milestone_due_date', String),
    Column('milestone_percentage', Float),
)

payment_schedules = Table(
    'payment_schedules', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('po_id', String, ForeignKey('purchase_orders.po_id')),
    Column('payment_date', String),
    Column('payment_amount', Float),
    Column('payment_description', String),
)
