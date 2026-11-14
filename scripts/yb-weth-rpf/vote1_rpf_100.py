"""
Curve ownership vote 1 of 2: set the reserved profit fraction (RPF) of the YieldBasis crvUSD/WETH pool to 100%.

Every profit raises lp_xcp_profit by RPF times its growth of virtual_price, and a rebalance must keep
virtual_price >= lp_xcp_profit. At 100% the rebalancing budget virtual_price - lp_xcp_profit stops growing: new
profit all goes to LPs, and rebalancing spends what has accumulated (plus donations). vote2_rpf_43.py returns the
RPF to 43% once that budget is almost spent. Curve vote 1525 only attaches the new policy to this pool and leaves
its RPF alone, so the two can execute in either order.

    uv run scripts/yb-weth-rpf/vote1_rpf_100.py           # fork simulation
    uv run scripts/yb-weth-rpf/vote1_rpf_100.py --live    # fork simulation, then create the vote

The fork simulation runs the action as the ownership agent with the checks below, then creates the vote, passes it
with Convex' veCRV and executes it with executeVote.
"""

import boa
from voting import OWNERSHIP, vote, vote_test

from common import POOL, RPF_43, RPF_100, budget, live_env, pool, set_rpf, show

DESCRIPTION = (
    f"Set the reserved profit fraction of the YieldBasis crvUSD/WETH pool ({POOL}) to 100% (from 43%). While it is "
    "100%, all new pool profit is kept for LPs, and rebalancing can only spend the profit already set aside for it "
    "(virtual_price above lp_xcp_profit) and donations. A follow-up vote returns the fraction to 43% once that "
    "budget is almost spent."
)

assert pool.reserved_profit_fraction() == RPF_43, "Unexpected RPF"
show()

with vote(OWNERSHIP, DESCRIPTION, live_env=live_env()):
    set_rpf(RPF_100)

    with vote_test():
        assert pool.reserved_profit_fraction() == RPF_100
        assert pool.admin_fee() == 0
        # A swap pays fees, which now raise lp_xcp_profit as much as virtual_price: the budget does not grow
        before = budget()
        crvusd = boa.from_etherscan(pool.coins(0), name="crvUSD")
        trader, amount = boa.env.generate_address(), pool.balances(0) // 100
        boa.deal(crvusd, trader, amount, adjust_supply=False)
        boa.env.time_travel(seconds=12)
        with boa.env.prank(trader):
            crvusd.approve(pool.address, amount)
            pool.exchange(0, 1, amount, 0)
        print("After the vote and a swap of 1% of the pool's crvUSD:")
        show()
        assert budget() <= before, "The budget grew at 100% RPF"

# The fork now holds the vote executed through executeVote
assert pool.reserved_profit_fraction() == RPF_100, "executeVote did not set the RPF to 100%"
print("Simulated vote passed and executed: RPF 100%")
