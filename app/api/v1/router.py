"""
Aggregate all v1 module routers in one place.
Add new feature routers here – main.py never needs to change.
"""

from fastapi import APIRouter

from app.modules.catalogue.routes import router as catalogue_router
from app.modules.goods_receipt.routes import router as gr_router
from app.modules.inventory.routes import router as inventory_router
from app.modules.label_parser.routes import router as label_router
from app.modules.purchase_order.routes import router as po_router

v1_router = APIRouter()

v1_router.include_router(label_router)
v1_router.include_router(catalogue_router)
v1_router.include_router(po_router)
v1_router.include_router(gr_router)
v1_router.include_router(inventory_router)
