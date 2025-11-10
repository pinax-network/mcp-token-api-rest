import copy


def patch_openapi_spec_for_keywords(spec: dict) -> dict:
    """
    Recursively searches an OpenAPI spec dictionary and renames properties
    that conflict with Python keywords.

    Specifically, it renames 'from' to 'from_'.

    Args:
        spec: The OpenAPI spec as a dictionary.

    Returns:
        A deep copy of the spec with conflicting keywords patched.
    """
    # Work on a copy to avoid modifying the original object in case it's used elsewhere
    patched_spec = copy.deepcopy(spec)

    # A map of common Python keywords that might conflict with API field names,
    # and their safe replacements. The convention is to add a trailing underscore.
    keyword_map = {
        "from": "from_",
        "in": "in_",
        "and": "and_",
        "or": "or_",
        "not": "not_",
        "is": "is_",
        "global": "global_",
        "import": "import_",
        "class": "class_",
        "as": "as_",
        "return": "return_",
        "async": "async_",
        "await": "await_",
    }

    if isinstance(patched_spec, dict):
        # Look for schemas with properties (most common case)
        if "properties" in patched_spec and isinstance(patched_spec["properties"], dict):
            properties = patched_spec["properties"]
            for keyword, replacement in keyword_map.items():
                if keyword in properties:
                    print(f"Patching keyword '{keyword}' to '{replacement}' in schema properties.")
                    # Rename the key
                    properties[replacement] = properties.pop(keyword)

        # Recurse into all values of the dictionary
        for key, value in patched_spec.items():
            patched_spec[key] = patch_openapi_spec_for_keywords(value)

    elif isinstance(patched_spec, list):
        # Recurse into all items in the list
        for i, item in enumerate(patched_spec):
            patched_spec[i] = patch_openapi_spec_for_keywords(item)

    return patched_spec
