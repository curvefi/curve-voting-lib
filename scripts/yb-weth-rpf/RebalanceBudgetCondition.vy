# pragma version 0.4.3
"""
@title RebalanceBudgetCondition
@license MIT
@notice Vote guard: reverts unless a Twocrypto pool has (almost) spent its rebalancing budget
@dev A rebalance must leave virtual_price >= lp_xcp_profit, so virtual_price - lp_xcp_profit is
     the profit the pool can still spend on moving price_scale (donations come on top). Every
     profit raises lp_xcp_profit by reserved_profit_fraction times its growth of virtual_price:
     at a 100% fraction the budget can only shrink.
"""


interface Twocrypto:
    def virtual_price() -> uint256: view
    def lp_xcp_profit() -> uint256: view


@external
def check(pool: Twocrypto, max_budget: uint256):
    """
    @notice Revert unless pool.virtual_price() - pool.lp_xcp_profit() <= max_budget
    @dev Not a view function, so that vote tooling captures the call as a vote action
    @param pool Twocrypto pool
    @param max_budget Largest budget allowed, in virtual_price units (10**18 = 1.0)
    """
    assert staticcall pool.virtual_price() <= staticcall pool.lp_xcp_profit() + max_budget, "Budget not spent"
