# This file is part of the faebryk project
# SPDX-License-Identifier: MIT


import logging
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Callable

from faebryk.core.parameter import (
    Abs,
    Add,
    Commutative,
    ConstrainableExpression,
    Difference,
    GreaterOrEqual,
    GreaterThan,
    Intersection,
    Is,
    IsSubset,
    Log,
    Multiply,
    Not,
    Or,
    ParameterOperatable,
    Power,
    Predicate,
    Round,
    Sin,
    SymmetricDifference,
    Union,
)
from faebryk.core.solver.utils import (
    CanonicalOperation,
    Contradiction,
    Mutator,
    alias_is_literal,
    alias_is_literal_and_check_predicate_eval,
    make_lit,
    no_other_constrains,
    remove_predicate,
    try_extract_all_literals,
    try_extract_boolset,
    try_extract_literal,
    try_extract_numeric_literal,
)
from faebryk.libs.sets.quantity_sets import Quantity_Interval_Disjoint
from faebryk.libs.sets.sets import BoolSet
from faebryk.libs.util import (
    cast_assert,
    find_or,
    not_none,
)

logger = logging.getLogger(__name__)

# TODO prettify

Literal = ParameterOperatable.Literal

# Arithmetic ---------------------------------------------------------------------------


def _fold_op(
    operands: Sequence[Literal],
    operator: Callable[[Literal, Literal], Literal],
    identity: Literal,
):
    """
    Return 'sum' of all literals in the iterable, or empty list if sum is identity.
    """
    if not operands:
        return []

    literal_it = iter(operands)
    const_sum = next(literal_it)
    for c in literal_it:
        const_sum = operator(const_sum, c)

    # TODO make work with all the types
    if const_sum == identity:
        return []

    return [const_sum]


def _collect_factors[T: Multiply | Power](
    counter: Counter[ParameterOperatable], collect_type: type[T]
):
    # collect factors
    factors: dict[ParameterOperatable, ParameterOperatable.NumberLiteral] = dict(
        counter.items()
    )

    same_literal_factors: dict[ParameterOperatable, list[T]] = defaultdict(list)

    for collect_op in set(factors.keys()):
        if not isinstance(collect_op, collect_type):
            continue
        # TODO unnecessary strict
        if len(collect_op.operands) != 2:
            continue
        if issubclass(collect_type, Commutative):
            if not any(
                ParameterOperatable.is_literal(operand)
                for operand in collect_op.operands
            ):
                continue
            paramop = next(
                o for o in collect_op.operands if not ParameterOperatable.is_literal(o)
            )
        else:
            if not ParameterOperatable.is_literal(collect_op.operands[1]):
                continue
            paramop = collect_op.operands[0]

        same_literal_factors[paramop].append(collect_op)
        if paramop not in factors:
            factors[paramop] = 0
        del factors[collect_op]

    new_factors = {}
    old_factors = []

    for var, count in factors.items():
        muls = same_literal_factors[var]
        mul_lits = [
            next(o for o in mul.operands if ParameterOperatable.is_literal(o))
            for mul in muls
        ]
        if count == 0 and len(muls) <= 1:
            old_factors.extend(muls)
            continue

        if count == 1 and not muls:
            old_factors.append(var)
            continue

        new_factors[var] = sum(mul_lits) + count  # type: ignore

    return new_factors, old_factors


def fold_add(
    expr: Add,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    """
    A + A + 5 + 10 -> 2*A + 15
    A + 5 + (-5) -> A
    A + (-A) + 5 -> Add(5)
    A + (3 * A) + 5 -> (4 * A) + 5
    A + (A * B * 2) -> A + (A * B * 2)
    #TODO think about -> A * (1 + B * 2) (factorization), not in here tho
    A + (B * 2) -> A + (B * 2)
    A + (A * 2) + (A * 3) -> (6 * A)
    A + (A * 2) + ((A *2 ) * 3) -> (3 * A) + (3 * (A * 2))
    #TODO recheck double match (of last case)
    """

    # A + X, B + X, X = A * 5
    # 6*A
    # (A * 2) + (A * 5)

    literal_sum = _fold_op(literal_operands, lambda a, b: a + b, 0)  # type: ignore #TODO

    new_factors, old_factors = _collect_factors(
        replacable_nonliteral_operands, Multiply
    )

    # if non-lit factors all 1 and no literal folding, nothing to do
    if not new_factors and len(literal_sum) == len(literal_operands):
        return

    # Careful, modifying old graph, but should be ok
    factored_operands = [Multiply(n, m) for n, m in new_factors.items()]

    new_operands = [
        *factored_operands,
        *old_factors,
        *literal_sum,
        *non_replacable_nonliteral_operands,
    ]

    # unpack if single operand (operatable)
    if len(new_operands) == 1 and isinstance(new_operands[0], ParameterOperatable):
        mutator._mutate(expr, mutator.get_copy(new_operands[0]))
        return

    new_expr = mutator.mutate_expression(
        expr, operands=new_operands, expression_factory=Add
    )

    # if only one literal operand, equal to it
    if len(new_operands) == 1:
        alias_is_literal(new_expr, new_operands[0])


def fold_multiply(
    expr: Multiply,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    literal_prod = _fold_op(literal_operands, lambda a, b: a * b, 1)  # type: ignore #TODO

    new_powers, old_powers = _collect_factors(replacable_nonliteral_operands, Power)

    # if non-lit powers all 1 and no literal folding, nothing to do
    if (
        not new_powers
        and len(literal_prod) == len(literal_operands)
        and not (
            literal_prod
            and literal_prod[0] == 0
            and len(replacable_nonliteral_operands)
            + len(non_replacable_nonliteral_operands)
            > 0
        )
    ):
        return

    # Careful, modifying old graph, but should be ok
    powered_operands = [Power(n, m) for n, m in new_powers.items()]

    new_operands = [
        *powered_operands,
        *old_powers,
        *literal_prod,
        *non_replacable_nonliteral_operands,
    ]

    zero_operand = any(try_extract_numeric_literal(o) == 0 for o in new_operands)
    if zero_operand:
        new_operands = [make_lit(0)]

    # unpack if single operand (operatable)
    if len(new_operands) == 1 and isinstance(new_operands[0], ParameterOperatable):
        mutator._mutate(expr, mutator.get_copy(new_operands[0]))
        return

    new_expr = mutator.mutate_expression(
        expr, operands=new_operands, expression_factory=Multiply
    )

    # if only one literal operand, equal to it
    if len(new_operands) == 1:
        alias_is_literal(new_expr, new_operands[0])


def fold_pow(
    expr: Power,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    """
    ```
    A^0 -> 1
    A^1 -> A
    0^A -> 0
    1^A -> 1
    5^3 -> 125
    #TODO rethink: 0^0 -> 1
    ```
    """

    # TODO if (litex0)^negative -> new constraint

    base, exp = map(try_extract_numeric_literal, expr.operands)
    # All literals
    if base is not None and exp is not None:
        alias_is_literal(expr, base**exp)
        return

    if exp is not None:
        if exp == 1:
            mutator._mutate(expr, mutator.get_copy(expr.operands[0]))
            return

        # in python 0**0 is also 1
        if exp == 0:
            alias_is_literal(expr, 1)
            return

    if base is not None:
        if base == 0:
            alias_is_literal(expr, 0)
            # FIXME: exp >! 0
            return
        if base == 1:
            alias_is_literal(expr, 1)
            return


# Setic --------------------------------------------------------------------------------
def fold_intersect(
    expr: Intersection,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    # TODO implement
    pass


def fold_union(
    expr: Union,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    # TODO implement
    pass


# Constrainable ------------------------------------------------------------------------


def fold_or(
    expr: Or,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    """
    ```
    Or(A, B, C, TrueEx) -> True
    Or(A, B, C, FalseEx) -> Or(A, B, C)
    Or(A, B, C, P) | P constrained -> True
    #TODO Or(A, B, A) -> Or(A, B)
    Or(P) -> P
    Or!(P) -> P!
    Or() -> False
    ```
    """

    extracted_literals = try_extract_all_literals(
        expr, lit_type=BoolSet, accept_partial=True
    )
    # Or(A, B, C, True) -> True
    if extracted_literals and BoolSet(True) in extracted_literals:
        alias_is_literal_and_check_predicate_eval(expr, True, mutator)
        return

    # Or() -> False
    if not expr.operands:
        alias_is_literal_and_check_predicate_eval(expr, False, mutator)
        return

    # Or(A, B, C, FalseEx) -> Or(A, B, C)
    # Or(A, B, A) -> Or(A, B)
    operands_not_clearly_false = {
        op
        for op in expr.operands
        if (lit := try_extract_boolset(op, allow_subset=True)) is None or True in lit
    }
    if len(operands_not_clearly_false) != len(expr.operands):
        # Rebuild without (False) literals
        mutator.mutate_expression(expr, operands=operands_not_clearly_false)
        return

    # Or(P) -> P
    if len(expr.operands) == 1:
        op = cast_assert(ParameterOperatable, expr.operands[0])
        out = cast_assert(
            ConstrainableExpression, mutator._mutate(expr, mutator.get_copy(op))
        )
        # Or(P!) -> P!
        if expr.constrained:
            out.constrain()
        return


def fold_not(
    expr: Not,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    """
    ```
    ¬(¬A) -> A
    ¬True -> False
    ¬False -> True
    ¬P | P constrained -> False

    ¬!(¬A v ¬B v C) -> ¬!(¬!A v ¬!B v C), ¬!C
    ```
    """
    # TODO ¬(A >= B) -> (B > A) ss ¬(A >= B) (only ss because of partial overlap)

    assert len(expr.operands) == 1

    lits = try_extract_all_literals(expr, lit_type=BoolSet)
    if lits:
        inner = lits[0]
        alias_is_literal_and_check_predicate_eval(expr, inner.op_not(), mutator)
        return

    op = expr.operands[0]
    if isinstance(op, ConstrainableExpression) and op.constrained and expr.constrained:
        raise Contradiction(expr)

    if replacable_nonliteral_operands:
        if isinstance(op, Not):
            inner = op.operands[0]
            # inner Not would have run first
            assert not isinstance(inner, BoolSet)
            mutator._mutate(expr, mutator.get_copy(inner))
            return

        # TODO this is kinda ugly
        # ¬!(¬A v ¬B v C) -> ¬!(¬!A v ¬!B v C), ¬!C
        if expr.constrained:
            # ¬( v )
            if isinstance(op, Or):
                for inner_op in op.operands:
                    # ¬(¬A v ...)
                    if isinstance(inner_op, Not):
                        for not_op in inner_op.operands:
                            if (
                                isinstance(not_op, ConstrainableExpression)
                                and not not_op.constrained
                            ):
                                cast_assert(
                                    ConstrainableExpression,
                                    mutator.get_copy(not_op),
                                ).constrain()
                    # ¬(A v ...)
                    elif isinstance(inner_op, ConstrainableExpression):
                        parent_nots = inner_op.get_operations(Not)
                        if parent_nots:
                            for n in parent_nots:
                                n.constrain()
                        else:
                            Not(mutator.get_copy(inner_op)).constrain()


def if_operands_same_make_true(pred: Predicate, mutator: Mutator) -> bool:
    if pred.operands[0] is not pred.operands[1]:
        return False
    if not isinstance(pred.operands[0], ParameterOperatable):
        return False
    alias_is_literal_and_check_predicate_eval(pred, True, mutator)
    return True


def fold_is(
    expr: Is,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    """
    ```
    A is A -> True
    A is X, A is Y | X != Y, X,Y lit -> Contradiction
    # predicates
    P is! True -> P!
    P is! False -> ¬!P
    P1 is! P2! -> P1!
    A is B | A or B unconstrained -> True
    # literals
    X is Y | X == Y -> True
    X is Y | X != Y -> False
    ```
    """

    # A is B -> R is R
    # A is E -> R is R, R is E
    # A is False, E is False
    #

    # A is A -> A is!! A
    if if_operands_same_make_true(expr, mutator):
        return

    # A is X, A is Y | X != Y -> Contradiction
    # is enough to check because of alias class merge
    lits = try_extract_all_literals(expr)

    # TODO Xex/Yex or X/Y enough?
    # Xex is Yex
    if lits is not None:
        a, b = lits
        alias_is_literal_and_check_predicate_eval(expr, a == b, mutator)
        return

    if expr.constrained:
        # P1 is! True -> P1!
        # P1 is! P2!  -> P1!
        if BoolSet(True) in literal_operands or any(
            op.constrained
            for op in expr.get_operatable_operands(ConstrainableExpression)
        ):
            for p in expr.get_operatable_operands(ConstrainableExpression):
                p.constrain()
        # P is! False -> ¬!P
        if BoolSet(False) in literal_operands:
            for p in expr.get_operatable_operands(ConstrainableExpression):
                Not(p).constrain()

    if not literal_operands:
        # TODO shouldn't this be the case for all predicates?
        # A is B | A or B unconstrained -> True
        if no_other_constrains(expr.operands[0], expr):
            alias_is_literal_and_check_predicate_eval(expr, True, mutator)
            return
        if no_other_constrains(expr.operands[1], expr):
            alias_is_literal_and_check_predicate_eval(expr, True, mutator)
            return


def fold_subset(
    expr: IsSubset,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    """
    ```
    A ss A -> True
    A is B, A ss B | B non(ex)literal -> repr(B, A)
    A as ([X]) -> A is ([X])
    # predicates
    P ss! True -> P!
    P ss! False -> ¬!P
    P1 ss! P2! -> P1!
    # literals
    X ss Y -> True / False

    # TODO A ss B, B ss/is C -> A ss C (transitive)
    ```
    """

    A, B = expr.operands

    # A as ([X]) -> A is ([X])
    b_is = try_extract_literal(B, allow_subset=False)
    if b_is is not None and b_is.is_single_element():
        new_is = mutator._mutate(expr, Is(mutator.get_copy(A), b_is))
        if expr.constrained:
            new_is.constrain()
        return

    # A is B, A ss B | B non(ex)literal -> repr(B, A)
    if not literal_operands:
        iss = cast_assert(ParameterOperatable, A).get_operations(
            Is, constrained_only=True
        )
        match_is_op = find_or(
            iss,
            lambda is_op: set(expr.operands).issubset(not_none(is_op).operands),
            default=None,
            default_multi=lambda dup: dup[0],
        )
        if match_is_op is not None:
            remove_predicate(expr, match_is_op, mutator)
            return

    if if_operands_same_make_true(expr, mutator):
        return

    a_is = try_extract_literal(A, allow_subset=False)
    a_ss = try_extract_literal(A, allow_subset=True)
    b = try_extract_literal(B, allow_subset=True)
    if b is None:
        return
    if a_is is not None:
        # A{I|X} ss B{S/I|Y} <-> X ss Y
        alias_is_literal_and_check_predicate_eval(expr, a_is.is_subset_of(b), mutator)  # type: ignore #TODO type
    elif a_ss is not None:
        if a_ss.is_subset_of(b):  # type: ignore #TODO type
            if b_is is not None:
                # A{S|X} ss B{I|Y} | X ss Y -> True
                alias_is_literal_and_check_predicate_eval(expr, True, mutator)

    if expr.constrained:
        # P1 ss! True -> P1!
        # P1 ss! P2!  -> P1!
        if (
            B == BoolSet(True)
            or isinstance(B, ConstrainableExpression)
            and B.constrained
        ):
            assert isinstance(A, ConstrainableExpression)
            A.constrain()
        # P ss! False -> ¬!P
        if B == BoolSet(False):
            assert isinstance(A, ConstrainableExpression)
            Not(A).constrain()


def fold_ge(
    expr: GreaterOrEqual,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
):
    """
    ```
    A >= A -> True
    # literals
    X >= Y -> [True] / [False] / [True, False]
    ```
    """
    if if_operands_same_make_true(expr, mutator):
        return

    lits = try_extract_all_literals(expr, lit_type=Quantity_Interval_Disjoint)
    if lits is None:
        return
    a, b = lits
    alias_is_literal_and_check_predicate_eval(expr, a >= b, mutator)


# Boilerplate --------------------------------------------------------------------------


def fold(
    expr: CanonicalOperation,
    literal_operands: Sequence[Literal],
    replacable_nonliteral_operands: Counter[ParameterOperatable],
    non_replacable_nonliteral_operands: Sequence[ParameterOperatable],
    mutator: Mutator,
) -> None:
    """
    literal_operands must be actual literals, not the literal the operand is aliased to!
    maybe it would be fine for set literals with one element?
    """

    def get_func[T: CanonicalOperation](
        expr: T,
    ) -> Callable[
        [
            T,
            Sequence[Literal],
            Counter[ParameterOperatable],
            Sequence[ParameterOperatable],
            Mutator,
        ],
        None,
    ]:
        # Arithmetic
        if isinstance(expr, Add):
            return fold_add  # type: ignore
        elif isinstance(expr, Multiply):
            return fold_multiply  # type: ignore
        elif isinstance(expr, Power):
            return fold_pow  # type: ignore
        elif isinstance(expr, Round):
            # TODO implement
            return lambda *args: None
        elif isinstance(expr, Abs):
            # TODO implement
            return lambda *args: None
        elif isinstance(expr, Sin):
            # TODO implement
            return lambda *args: None
        elif isinstance(expr, Log):
            # TODO implement
            return lambda *args: None
        # Logic
        elif isinstance(expr, Or):
            return fold_or  # type: ignore
        elif isinstance(expr, Not):
            return fold_not  # type: ignore
        # Equality / Inequality
        elif isinstance(expr, Is):
            return fold_is  # type: ignore
        elif isinstance(expr, GreaterOrEqual):
            return fold_ge  # type: ignore
        elif isinstance(expr, GreaterThan):
            # TODO implement
            return lambda *args: None
        elif isinstance(expr, IsSubset):
            return fold_subset  # type: ignore
        # Sets
        elif isinstance(expr, Intersection):
            return fold_intersect  # type: ignore
        elif isinstance(expr, Union):
            return fold_union  # type: ignore
        elif isinstance(expr, SymmetricDifference):
            # TODO implement
            return lambda *args: None
        elif isinstance(expr, Difference):
            # TODO implement
            return lambda *args: None

        raise ValueError(f"unsupported operation: {expr}")

    get_func(expr)(
        expr,
        literal_operands,
        replacable_nonliteral_operands,
        non_replacable_nonliteral_operands,
        mutator,
    )
