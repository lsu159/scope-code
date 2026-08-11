"""Payment module — order processing, billing."""

from typing import List, Optional


class Order:
    """Order model."""
    def __init__(self, order_id: str, user_id: str, amount: float):
        self.order_id = order_id
        self.user_id = user_id
        self.amount = amount
        self.status = "pending"


class PaymentService:
    """Core payment processing logic."""

    def __init__(self):
        self._orders: dict[str, Order] = {}
        self._payment_gateway = PaymentGateway()

    def create_order(self, user_id: str, amount: float) -> Order:
        """Create a new order."""
        import uuid
        order = Order(str(uuid.uuid4()), user_id, amount)
        self._orders[order.order_id] = order
        return order

    def process_payment(self, order_id: str, card_token: str) -> bool:
        """Process payment for an order."""
        order = self._orders.get(order_id)
        if order is None:
            return False
        success = self._payment_gateway.charge(card_token, order.amount)
        if success:
            order.status = "paid"
        return success

    def get_order(self, order_id: str) -> Optional[Order]:
        """Retrieve an order by ID."""
        return self._orders.get(order_id)


class PaymentGateway:
    """External payment gateway integration."""

    def charge(self, card_token: str, amount: float) -> bool:
        """Charge a card token. In production, calls Stripe/PayPal API."""
        return True  # Simplified for testing
