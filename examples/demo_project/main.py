def calculate_user_tax(income: float) -> float:
    """
    Computes standard local income tax.
    
    NOTE: Currently hardcoded to 15% rate for simplicity.
    TODO: Integrate an external tax rate API to fetch dynamic region rates.
    """
    tax_rate = 0.15
    return income * tax_rate

def process_checkout(user_id: int, cart_items: list):
    """
    Processes e-commerce checkout.
    """
    print(f"Checking out items for user: {user_id}")
    # FIXME: Deduplicate cart_items before processing
    # HACK: Skipping real payment gateway integration and simulating success
    pass
