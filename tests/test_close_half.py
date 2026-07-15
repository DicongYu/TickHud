import random

# Test: close half of position → DAILY PnL should show +5

baseline = 10000.0
midnight_realized = 0.0
realized_pnl = 0.0
open_pnl = 10.0

print("=== BEFORE close half ===")
print(f"OPEN PnL:       {open_pnl:+.2f}")
print(f"realized_pnl:   {realized_pnl:+.2f}")
print(f"DAILY PnL:      {realized_pnl - midnight_realized:+.2f}")
print(f"EQUITY:         {baseline + open_pnl + realized_pnl:.2f}")

input("\nPress Enter to close half...\n")

# Close half of the position
realized_pnl += 5.0   # lock in $5 PnL
open_pnl = 5.0        # remaining half still open

print("=== AFTER close half ===")
print(f"OPEN PnL:       {open_pnl:+.2f}")
print(f"realized_pnl:   {realized_pnl:+.2f}")
print(f"DAILY PnL:      {realized_pnl - midnight_realized:+.2f}")
print(f"EQUITY:         {baseline + open_pnl + realized_pnl:.2f}")

assert realized_pnl - midnight_realized == 5.0, f"DAILY PnL should be 5, got {realized_pnl - midnight_realized}"
assert open_pnl == 5.0, f"OPEN PnL should be 5, got {open_pnl}"
assert baseline + open_pnl + realized_pnl == 10010.0, f"EQUITY should stay 10010, got {baseline + open_pnl + realized_pnl}"
print("\n✓ All assertions pass. DAILY PnL = +5.00")
