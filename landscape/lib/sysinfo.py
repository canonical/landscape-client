

def get_memory_info(filename="/prov/meminfo"):
    """Gets data in megabytes and returns a C{(memory, swap)} tuple."""
    data = {}
    for line in open(filename):
        if line != "\n":
            parts = line.split(":")
            key = parts[0]

            if key in ["Active", "MemTotal", "SwapFree"]:
                value = int(parts[1].strip().split(" ")[0])
                data[key] = value

    free_memory = data["MemTotal"] - data["Active"]
    free_swap = data["SwapFree"]
    return (free_memory // 1024, free_swap // 1024)
