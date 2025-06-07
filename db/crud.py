from sqlalchemy.ext.asyncio import AsyncSession
from db.models import PurchaseOrder
from sqlalchemy.future import select

async def create_purchase_order(db: AsyncSession, po_data: dict) -> PurchaseOrder:
    po = PurchaseOrder(**po_data)
    db.add(po)
    await db.commit()
    await db.refresh(po)
    return po

async def get_po_by_po_id(db: AsyncSession, po_id: str) -> PurchaseOrder | None:
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_id == po_id))
    return result.scalars().first()
