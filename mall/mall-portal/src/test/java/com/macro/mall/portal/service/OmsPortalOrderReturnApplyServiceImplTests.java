package com.macro.mall.portal.service;

import com.macro.mall.mapper.OmsOrderItemMapper;
import com.macro.mall.mapper.OmsOrderMapper;
import com.macro.mall.mapper.OmsOrderReturnApplyMapper;
import com.macro.mall.model.OmsOrder;
import com.macro.mall.model.OmsOrderItem;
import com.macro.mall.model.OmsOrderReturnApply;
import com.macro.mall.model.UmsMember;
import com.macro.mall.portal.domain.OmsOrderReturnApplyParam;
import com.macro.mall.portal.dao.OmsPortalOrderReturnApplyDao;
import com.macro.mall.portal.service.impl.OmsPortalOrderReturnApplyServiceImpl;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OmsPortalOrderReturnApplyServiceImplTests {
    @Mock
    private OmsOrderReturnApplyMapper returnApplyMapper;
    @Mock
    private OmsPortalOrderReturnApplyDao returnApplyDao;
    @Mock
    private OmsOrderMapper orderMapper;
    @Mock
    private OmsOrderItemMapper orderItemMapper;
    @Mock
    private UmsMemberService memberService;
    @InjectMocks
    private OmsPortalOrderReturnApplyServiceImpl service;

    @Test
    void createUsesCurrentMemberAndOrderSnapshot() throws Exception {
        UmsMember member = new UmsMember();
        member.setId(100L);
        member.setUsername("member100");
        when(memberService.getCurrentMember()).thenReturn(member);

        OmsOrder order = new OmsOrder();
        order.setId(65L);
        order.setOrderSn("ORD1001");
        order.setMemberId(100L);
        order.setMemberUsername("member100");
        order.setReceiverName("张三");
        order.setReceiverPhone("13800000000");
        order.setStatus(2);
        when(orderMapper.selectByExample(any())).thenReturn(Collections.singletonList(order));

        OmsOrderItem item = new OmsOrderItem();
        item.setOrderId(65L);
        item.setProductId(501L);
        item.setProductName("测试商品");
        item.setProductBrand("测试品牌");
        item.setProductQuantity(1);
        item.setProductPrice(new BigDecimal("399.00"));
        item.setRealAmount(new BigDecimal("359.00"));
        when(orderItemMapper.selectByExample(any())).thenReturn(Collections.singletonList(item));
        when(returnApplyMapper.insertSelective(any())).thenAnswer(invocation -> {
            OmsOrderReturnApply apply = invocation.getArgument(0);
            apply.setId(9001L);
            return 1;
        });

        OmsOrderReturnApplyParam param = new OmsOrderReturnApplyParam();
        param.setOrderSn("ORD1001");
        param.setProductId(501L);
        param.setReason("不想要了");
        param.getClass().getMethod("setApplyType", String.class).invoke(param, "return");
        param.getClass().getMethod("setIdempotencyKey", String.class).invoke(param, "idem-1");

        Object result = service.create(param);

        OmsOrderReturnApply created = assertInstanceOf(OmsOrderReturnApply.class, result);
        assertEquals(9001L, created.getId());
        assertEquals(65L, created.getOrderId());
        assertEquals("member100", created.getMemberUsername());
        assertEquals("测试商品", created.getProductName());
        assertEquals(new BigDecimal("359.00"), created.getReturnAmount());
        assertEquals("return", created.getClass().getMethod("getApplyType").invoke(created));
    }

    @Test
    void listActiveByOrderSnsUsesCurrentMemberAndBoundedOrderNumbers() {
        UmsMember member = new UmsMember();
        member.setId(100L);
        when(memberService.getCurrentMember()).thenReturn(member);
        List<String> orderSns = Arrays.asList("ORD1001", "ORD1002");
        OmsOrderReturnApply activeApply = new OmsOrderReturnApply();
        activeApply.setId(9001L);
        when(returnApplyDao.listActiveByOrderSns(100L, orderSns))
                .thenReturn(Collections.singletonList(activeApply));

        List<OmsOrderReturnApply> result = service.listActiveByOrderSns(orderSns);

        assertEquals(Collections.singletonList(activeApply), result);
        verify(returnApplyDao).listActiveByOrderSns(100L, orderSns);
    }
}
