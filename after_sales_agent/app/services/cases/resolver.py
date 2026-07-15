from __future__ import annotations

from services.cases.context import AfterSalesCase, ProductCandidate, ProductResolution


async def resolve_product_reference(
    case: AfterSalesCase, message: str, gateway
) -> ProductResolution:
    """只在 Case 已绑定订单的范围内解析商品指代，绝不猜测全局商品 ID。"""

    if not case.order_id:
        return ProductResolution(requires_selection=True)

    order = await gateway.get_order(case.order_id, case.user_id)
    if order is None:
        return ProductResolution(requires_selection=True)

    candidates = [
        ProductCandidate(
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=item.quantity,
            price=item.price,
        )
        for item in order.items
    ]
    case.product_candidates = candidates

    if case.product_id:
        selected = next(
            (item for item in candidates if item.product_id == case.product_id), None
        )
        if selected:
            case.product_name = selected.product_name
            return ProductResolution(
                product_id=selected.product_id, product_name=selected.product_name
            )

    if len(candidates) == 1:
        return _select(case, candidates[0])

    normalized = "".join(message.lower().split())
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(candidates):
            return _select(case, candidates[index])

    matches = [item for item in candidates if _matches_product_name(normalized, item.product_name)]
    if len(matches) == 1:
        return _select(case, matches[0])

    return ProductResolution(candidates=candidates, requires_selection=True)


def _select(case: AfterSalesCase, candidate: ProductCandidate) -> ProductResolution:
    case.product_id = candidate.product_id
    case.product_name = candidate.product_name
    return ProductResolution(
        product_id=candidate.product_id, product_name=candidate.product_name
    )


def _matches_product_name(message: str, product_name: str) -> bool:
    normalized_name = "".join(product_name.lower().split())
    if not normalized_name:
        return False
    if normalized_name in message:
        return True
    return any(
        fragment in message
        for fragment in (normalized_name[index : index + 2] for index in range(len(normalized_name) - 1))
        if len(fragment.strip()) == 2
    )
