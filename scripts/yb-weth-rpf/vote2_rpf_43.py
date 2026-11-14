"""
Curve ownership vote 2 of 2: return the reserved profit fraction (RPF) of the YieldBasis crvUSD/WETH pool from the
100% of vote 1 to 43%, where Curve vote 1525 leaves it, once the pool has almost spent its rebalancing budget.

A rebalance must keep virtual_price >= lp_xcp_profit, and every profit raises lp_xcp_profit by RPF times its growth
of virtual_price. At 100% RPF the budget virtual_price - lp_xcp_profit stops growing, and rebalancing spends it.
CallComparator compares one view against a constant, which cannot express this budget: virtual_price and
lp_xcp_profit both grow with every fee. RebalanceBudgetCondition.check(pool, max_budget) reverts unless
virtual_price <= lp_xcp_profit + max_budget.

Actions:
    1. CallComparator.check_equal(pool, reserved_profit_fraction(), 100%): vote 1 has executed
    2. RebalanceBudgetCondition.check(pool, MAX_BUDGET): the budget is almost spent
    3. proxy.execute(pool, set_fee_parameters(43%, 0))
Until 1 and 2 hold, executeVote reverts; the vote stays executable.

A rebalance step costs ~0.004% of virtual_price at the largest step (0.5%), so a 0.1% MAX_BUDGET is reachable, and
the pool keeps rebalancing while it waits for someone to execute this vote.

The fork simulation brings the pool to the state this vote is meant for: it passes vote 1525 and vote 1 (applies
vote 1's action if VOTE_1 is not set), checks that the actions revert before vote 1 and while the budget is large,
then writes lp_xcp_profit to leave a budget of exactly MAX_BUDGET. The vote is then created, passed with Convex'
veCRV and executed with executeVote.

    uv run scripts/yb-weth-rpf/vote2_rpf_43.py           # fork simulation
    uv run scripts/yb-weth-rpf/vote2_rpf_43.py --live    # fork simulation, then create the vote (set CONDITION
                                                          # and VOTE_1 first)
"""

import json
import os

import boa
from vyper.utils import method_id
from voting import OWNERSHIP, vote, vote_test

from common import (CALL_COMPARATOR, LIVE, POOL, PROXY, RPF_43, RPF_100, VOTE_1525, live_env, pass_vote, pool,
                    set_rpf, show, voting)

CONDITION = None  # RebalanceBudgetCondition deployed by deploy_condition.py; if None, deployed on the fork
VOTE_1 = None  # Curve vote created by vote1_rpf_100.py
MAX_BUDGET = 10**15  # 0.1% in virtual_price units
LP_XCP_PROFIT_SLOT = 23  # fork only: storage layout of the pool's verified source

assert not LIVE or (CONDITION and VOTE_1), "Set CONDITION and VOTE_1 before creating the vote"

deployer = boa.load_partial(os.path.join(os.path.dirname(os.path.abspath(__file__)), "RebalanceBudgetCondition.vy"))
if CONDITION:
    assert boa.env.get_code(CONDITION) == deployer.compiler_data.bytecode_runtime, "CONDITION is not this source"
    address = CONDITION
else:
    address = deployer.deploy().address
# Bound through its ABI: curve-voting-lib only captures calls to ABI contracts, not to Vyper source contracts
condition = boa.loads_abi(json.dumps(deployer.at(address).abi), name="RebalanceBudgetCondition").at(address)
comparator = boa.from_etherscan(CALL_COMPARATOR, name="CallComparator")

DESCRIPTION = (
    f"Return the reserved profit fraction of the YieldBasis crvUSD/WETH pool ({POOL}) to 43% from the 100% set by "
    f"vote {VOTE_1}. The vote can only execute once the pool has almost spent its rebalancing budget: it first asks "
    f"CallComparator ({comparator.address}) to check that the fraction is still 100%, then RebalanceBudgetCondition "
    f"({condition.address}) to check that virtual_price exceeds lp_xcp_profit by at most {MAX_BUDGET / 1e18:.1%}. "
    "Until then executeVote reverts, and the vote can be executed later."
)


def actions():
    comparator.check_equal(pool.address, method_id("reserved_profit_fraction()"), RPF_100)
    condition.check(pool.address, MAX_BUDGET)
    set_rpf(RPF_43)


def expect_revert(reason: str):
    with boa.env.anchor(), boa.env.prank(OWNERSHIP.agent):
        try:
            actions()
        except boa.BoaError as e:
            assert reason in str(e), e
            print(f"  reverts: {reason}")
            return
    raise AssertionError("Vote 2 did not revert")


def spend_budget():
    """Fork only: the state once rebalancing has spent the budget down to MAX_BUDGET"""
    assert boa.env.get_storage(pool.address, LP_XCP_PROFIT_SLOT) == pool.lp_xcp_profit(), "Wrong slot"
    boa.env.set_storage(pool.address, LP_XCP_PROFIT_SLOT, pool.virtual_price() - MAX_BUDGET)


show()
pass_vote(VOTE_1525)
assert pool.reserved_profit_fraction() == RPF_43, f"Vote {VOTE_1525} changed the RPF"

print("Before vote 1, with the budget spent:")
with boa.env.anchor():
    spend_budget()
    expect_revert("Not equal")

if VOTE_1:
    pass_vote(VOTE_1)
else:
    with boa.env.prank(OWNERSHIP.agent):
        set_rpf(RPF_100)
assert pool.reserved_profit_fraction() == RPF_100, "Vote 1 did not set the RPF to 100%"

print("After vote 1, with the budget not spent:")
show()
expect_revert("Budget not spent")

print("After vote 1, with the budget spent:")
spend_budget()
show()

with vote(OWNERSHIP, DESCRIPTION, live_env=live_env()):
    actions()

    with vote_test():
        assert pool.reserved_profit_fraction() == RPF_43
        assert pool.admin_fee() == 0

# The fork now holds the vote executed through executeVote. It must make all three calls (a call the library did
# not capture would be missing)
script = voting.getVote(voting.votesLength() - 1)[9]
for target in (comparator.address, condition.address, PROXY):
    assert bytes.fromhex(target[2:]) in script, f"The vote does not call {target}"
assert pool.reserved_profit_fraction() == RPF_43, "executeVote did not set the RPF to 43%"
print("Simulated vote passed and executed: it calls CallComparator, RebalanceBudgetCondition and the proxy; RPF 43%")
