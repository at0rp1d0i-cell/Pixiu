from src.agents.validator import _check_no_future_leak, _check_valid_fields, _check_log_safety
import sys
import logging

logging.basicConfig(level=logging.INFO)
print("=== EXPERIMENT 4: VALIDATOR CONSTRAINTS ===")

test1, msg1 = _check_no_future_leak("Ref($close, -1)")
print(f"Test 1 (Negative Ref): Passed={test1}, Msg={msg1}")

test2, msg2 = _check_valid_fields("Mean($price, 5)")
print(f"Test 2 (Invalid Field $price): Passed={test2}, Msg={msg2}")

test3, msg3 = _check_log_safety("Log($close - Ref($close, 1))")
print(f"Test 3 (Negative Log): Passed={test3}, Msg={msg3}")

test4, msg4 = _check_valid_fields("Mean($close, 5)")
print(f"Test 4 (Valid Field $close): Passed={test4}, Msg={msg4}")

if not test1 and not test2 and not test3 and test4:
    print("\n✅ All constraints worked as expected.")
    sys.exit(0)
else:
    print("\n❌ Constraints failed.")
    sys.exit(1)
