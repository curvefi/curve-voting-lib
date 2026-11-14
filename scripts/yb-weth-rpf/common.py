"""
Shared setup for the YieldBasis crvUSD/WETH reserved profit fraction (RPF) votes.

Settings come from config.py next to this file (gitignored; copy config.py.example). Every run forks RPC_URL
and simulates there; --live then sends the transaction from KEYSTORE.
"""

import json
import os
import sys
from getpass import getpass

import boa
from eth_account import Account
from voting import CustomEnv, OWNERSHIP, abi, vote_test
from voting.config import CONVEX_VOTER_PROXY

try:
    from config import ETHERSCAN_API_KEY, KEYSTORE, PINATA_JWT, RPC_URL
except ImportError:
    sys.exit("Copy config.py.example to config.py in scripts/yb-weth-rpf and fill it in")

LIVE = "--live" in sys.argv[1:]

POOL = "0x656341Ef90b622c6634e0573772FfB7f3669b9f3"  # YieldBasis crvUSD/WETH Twocrypto
PROXY = "0xeDA0108D5bB8cdE2ba4A59E22F3Ed5d211C77187"  # AmmOwnerProxy: factory admin, owned by the ownership agent
CALL_COMPARATOR = "0xd3BFa85dc668Aab38121bE12D69dd180301dec25"  # YieldBasis CallComparator
VOTE_1525 = 1525  # attaches the new YBOraclizedPolicy to the pool, leaves its RPF alone

FEE_PRECISION = 10**10
RPF_100 = FEE_PRECISION
RPF_43 = 43 * FEE_PRECISION // 100  # the RPF now and after vote 1525

boa.fork(RPC_URL)
boa.set_etherscan(api_key=ETHERSCAN_API_KEY)
pool = boa.from_etherscan(POOL, name="Twocrypto")
proxy = boa.from_etherscan(PROXY, name="AmmOwnerProxy")
voting = abi.voting.at(OWNERSHIP.voting)
assert proxy.dao().lower() == OWNERSHIP.agent.lower(), "The ownership agent does not own the proxy"
assert pool.admin_fee() == 0, "Admin fee is not 0"


def budget() -> int:
    """Profit the pool can still spend on rebalancing: a rebalance must keep virtual_price >= lp_xcp_profit"""
    return pool.virtual_price() - pool.lp_xcp_profit()


def show():
    print(f"  RPF {pool.reserved_profit_fraction() / FEE_PRECISION:.2%}, virtual_price {pool.virtual_price() / 1e18:.6f}, "
          f"lp_xcp_profit {pool.lp_xcp_profit() / 1e18:.6f}, rebalancing budget {budget() / 1e18:.4%}")


def set_rpf(rpf: int):
    """Pool admin call through the proxy: only proxy.execute is captured as a vote action"""
    with vote_test():
        calldata = pool.set_fee_parameters.prepare_calldata(rpf, 0)
    proxy.execute(pool.address, calldata)


def pass_vote(vote_id: int):
    """Fork only: pass and execute a Curve ownership vote with Convex' veCRV"""
    _, executed, start = voting.getVote(vote_id)[:3]
    if executed:
        return
    with boa.env.prank(CONVEX_VOTER_PROXY):
        voting.vote(vote_id, True, False)
    end = start + voting.voteTime()
    if boa.env.evm.patch.timestamp <= end:
        boa.env.time_travel(seconds=end - boa.env.evm.patch.timestamp + 1)
    voting.executeVote(vote_id)
    print(f"Fork: passed and executed vote {vote_id}")


def load_account():
    with open(os.path.expanduser(f"~/.brownie/accounts/{KEYSTORE}.json")) as f:
        return Account.from_key(Account.decrypt(json.load(f), getpass(f"Password for {KEYSTORE}: ")))


def live_env():
    """With --live, the vote is created from KEYSTORE once the fork simulation passes (after ENTER)"""
    if not LIVE:
        return None
    assert PINATA_JWT, "Set PINATA_JWT in config.py"
    os.environ["PINATA_JWT"] = PINATA_JWT  # curve-voting-lib reads it from the process environment
    return CustomEnv(RPC_URL, load_account())
