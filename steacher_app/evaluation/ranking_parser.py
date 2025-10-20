
def parse_ranking(ranking_input: str) -> dict:
    """
    Parse ranking input string with tie support into a rank dictionary.
    
    Supports two formats:
    - Simple: "abcd" means a=1st, b=2nd, c=3rd, d=4th
    - Ties: "(ab)cd" means a and b tied for 1st, c=3rd, d=4th
    
    When items are tied, they all get the same rank, and subsequent ranks skip
    appropriately (e.g., if two items tie for 1st, the next item is 3rd, not 2nd).
    
    Args:
        ranking_input: Ranking string like "abcd" or "(ab)cd"
        
    Returns:
        Dict mapping letters to ranks, e.g., {"a": 1, "b": 1, "c": 3, "d": 4}
        
    Raises:
        ValueError: If parentheses are unmatched
    """
    ranking_input = ranking_input.strip().lower()
    ranks = {}
    current_rank = 1
    i = 0

    while i < len(ranking_input):
        if ranking_input[i] == '(':
            # Find matching )
            j = ranking_input.find(')', i)
            if j == -1:
                raise ValueError("Unmatched parenthesis")
            tied_letters = [c for c in ranking_input[i+1:j] if c.isalpha()]
            for letter in tied_letters:
                ranks[letter] = current_rank
            current_rank += len(tied_letters)
            i = j + 1
        elif ranking_input[i].isalpha():
            ranks[ranking_input[i]] = current_rank
            current_rank += 1
            i += 1
        else:
            i += 1

    return ranks


def validate_ranking(ranking_input: str, expected_letters: set) -> tuple:
    """
    Validate that ranking input contains exactly the expected letters.
    
    Checks that the parsed ranking includes all required letters (no more, no less)
    and that the input can be successfully parsed. Used to ensure evaluators rank
    all models before submitting.
    
    Args:
        ranking_input: Ranking string to validate (e.g., "abcd" or "(ab)cd")
        expected_letters: Set of letters that must be ranked (e.g., {'a', 'b', 'c', 'd'})
        
    Returns:
        Tuple of (is_valid: bool, error_message: str). If valid, error_message is empty.
        Error messages describe missing or invalid letters.
    """
    try:
        ranks = parse_ranking(ranking_input)
        found_letters = set(ranks.keys())

        if found_letters != expected_letters:
            missing = expected_letters - found_letters
            extra = found_letters - expected_letters
            msg = []
            if missing:
                msg.append(f"Missing: {', '.join(sorted(missing))}")
            if extra:
                msg.append(f"Invalid: {', '.join(sorted(extra))}")
            return False, "; ".join(msg)

        return True, ""
    except Exception as e:
        return False, str(e)

