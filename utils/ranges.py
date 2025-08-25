def list_to_ranges(nums):
    if not nums:
        return ""
    
    # Sort the list to handle unsorted input
    nums = sorted(set(nums))  # Remove duplicates and sort
    
    ranges = []
    start = nums[0]
    end = nums[0]
    
    for i in range(1, len(nums)):
        if nums[i] == end + 1:
            # Continue the current range
            end = nums[i]
        else:
            # End the current range and start a new one
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{end}")
            start = nums[i]
            end = nums[i]
    
    # Handle the last range
    if start == end:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{end}")
    
    return ",".join(ranges)


if __name__ == "__main__":
    print(list_to_ranges([1, 2, 3, 5, 7, 8, 9]))  # Output: "1-3,5,7-9"