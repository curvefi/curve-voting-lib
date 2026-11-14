"""
Deploy RebalanceBudgetCondition (needed by vote2_rpf_43.py) and verify it on Etherscan.

    uv run scripts/yb-weth-rpf/deploy_condition.py           # fork test only
    uv run scripts/yb-weth-rpf/deploy_condition.py --live    # fork test, then deploy from KEYSTORE
"""

import os

import boa
from boa.explorer import Etherscan

from common import ETHERSCAN_API_KEY, KEYSTORE, LIVE, RPC_URL, budget, load_account, pool, show

SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "RebalanceBudgetCondition.vy")

condition = boa.load(SOURCE)
show()
condition.check(pool.address, budget())
with boa.reverts("Budget not spent"):
    condition.check(pool.address, budget() - 1)
print("Fork: the condition passes at the current budget and reverts below it")

if LIVE:
    boa.set_network_env(RPC_URL)
    boa.env.add_account(load_account())
    input(f"Press ENTER to deploy from {KEYSTORE} ({boa.env.eoa})")
    condition = boa.load(SOURCE)
    print(f"RebalanceBudgetCondition: {condition.address}")
    boa.verify(condition, Etherscan(api_key=ETHERSCAN_API_KEY), wait=True)
