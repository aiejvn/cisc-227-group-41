class Equipment:
    def __init__(self, id, name, category, total_units, available_units, is_available=True, needs_deposit=False):
        self.id = id
        self.name = name
        self.category = category
        self.total_units = total_units
        self.available_units = available_units
        self.is_available = is_available  # False when out-of-service / under repair
        self.needs_deposit = needs_deposit  # True when checkout must include a deposit

    def deposit_flag_locked(self):
        """
            The needs_deposit flag can only change while no units are rented out.
            This is to prevent cases where a store employee changes the `need_deposit` flag 
            of a piece of equipment while a customer is renting it (equipment suddenly needs
            deposit, or suddenly does not need deposit). 
        """
        return self.available_units != self.total_units

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "total_units": self.total_units,
            "available_units": self.available_units,
            "is_available": self.is_available,
            "needs_deposit": self.needs_deposit,
        }
