from adapters.ecommerce_gateway import EcommerceGateway
from adapters.mall_gateway import MallEcommerceGateway


def test_mall_gateway_implements_shared_ecommerce_gateway_contract():
    assert isinstance(MallEcommerceGateway(auth_token="test-token"), EcommerceGateway)
