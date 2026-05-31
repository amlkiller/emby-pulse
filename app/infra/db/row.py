class DataRow(dict):
    """Dict row with sqlite3.Row-like index access and case-insensitive keys."""

    def __init__(self, original_dict):
        super().__init__(original_dict)
        self._vals = list(original_dict.values())
        self._lower_keys = {str(k).lower(): k for k in original_dict.keys()}

    def __getitem__(self, key):
        if isinstance(key, int):
            try:
                return self._vals[key]
            except IndexError:
                return None

        key_str = str(key)
        if super().__contains__(key_str):
            return super().__getitem__(key_str)

        key_lower = key_str.lower()
        if key_lower in self._lower_keys:
            return super().__getitem__(self._lower_keys[key_lower])
        return None


def to_data_row(row):
    if row is None:
        return None
    if isinstance(row, DataRow):
        return row
    if hasattr(row, "keys"):
        return DataRow({key: row[key] for key in row.keys()})
    if isinstance(row, dict):
        return DataRow(row)
    return row
