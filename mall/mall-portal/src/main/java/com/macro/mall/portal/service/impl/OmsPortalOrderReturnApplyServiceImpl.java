package com.macro.mall.portal.service.impl;

import cn.hutool.core.collection.CollUtil;
import com.github.pagehelper.PageHelper;
import com.macro.mall.common.exception.Asserts;
import com.macro.mall.mapper.OmsOrderItemMapper;
import com.macro.mall.mapper.OmsOrderMapper;
import com.macro.mall.mapper.OmsOrderReturnApplyMapper;
import com.macro.mall.model.*;
import com.macro.mall.portal.dao.OmsPortalOrderReturnApplyDao;
import com.macro.mall.portal.domain.OmsOrderReturnApplyParam;
import com.macro.mall.portal.service.OmsPortalOrderReturnApplyService;
import com.macro.mall.portal.service.UmsMemberService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class OmsPortalOrderReturnApplyServiceImpl implements OmsPortalOrderReturnApplyService {
    @Autowired
    private OmsOrderReturnApplyMapper returnApplyMapper;
    @Autowired
    private OmsPortalOrderReturnApplyDao returnApplyDao;
    @Autowired
    private OmsOrderMapper orderMapper;
    @Autowired
    private OmsOrderItemMapper orderItemMapper;
    @Autowired
    private UmsMemberService memberService;

    @Override
    public OmsOrderReturnApply create(OmsOrderReturnApplyParam param) {
        UmsMember member = memberService.getCurrentMember();
        String type = param.getApplyType();
        if (!Arrays.asList("refund", "return", "exchange").contains(type)) {
            Asserts.fail("售后类型只能是退款、退货或换货");
        }
        if (!StringUtils.hasText(param.getReason()) || param.getReason().length() > 200) {
            Asserts.fail("售后原因不能为空且不能超过200个字符");
        }
        if (param.getProductId() == null) {
            Asserts.fail("商品编号不能为空");
        }
        if (StringUtils.hasText(param.getIdempotencyKey())) {
            OmsOrderReturnApply existing = returnApplyDao.getByIdempotencyKey(member.getId(), param.getIdempotencyKey());
            if (existing != null) {
                return existing;
            }
        }

        OmsOrderExample orderExample = new OmsOrderExample();
        OmsOrderExample.Criteria orderCriteria = orderExample.createCriteria()
                .andMemberIdEqualTo(member.getId()).andDeleteStatusEqualTo(0);
        if (StringUtils.hasText(param.getOrderSn())) {
            orderCriteria.andOrderSnEqualTo(param.getOrderSn());
        } else if (param.getOrderId() != null) {
            orderCriteria.andIdEqualTo(param.getOrderId());
        } else {
            Asserts.fail("订单号不能为空");
        }
        List<OmsOrder> orders = orderMapper.selectByExample(orderExample);
        if (CollUtil.isEmpty(orders)) {
            Asserts.fail("订单不存在或不属于当前用户");
        }
        OmsOrder order = orders.get(0);
        if (("refund".equals(type) && order.getStatus() != 1)
                || (!"refund".equals(type) && order.getStatus() != 2 && order.getStatus() != 3)) {
            Asserts.fail("当前订单状态不支持该售后类型");
        }

        OmsOrderItemExample itemExample = new OmsOrderItemExample();
        itemExample.createCriteria().andOrderIdEqualTo(order.getId()).andProductIdEqualTo(param.getProductId());
        List<OmsOrderItem> items = orderItemMapper.selectByExample(itemExample);
        if (CollUtil.isEmpty(items)) {
            Asserts.fail("该商品不属于当前订单");
        }
        OmsOrderItem item = items.get(0);
        BigDecimal realPrice = item.getRealAmount() == null ? item.getProductPrice() : item.getRealAmount();

        OmsOrderReturnApply apply = new OmsOrderReturnApply();
        apply.setMemberId(member.getId());
        apply.setMemberUsername(member.getUsername());
        apply.setApplyType(type);
        apply.setIdempotencyKey(param.getIdempotencyKey());
        apply.setOrderId(order.getId());
        apply.setOrderSn(order.getOrderSn());
        apply.setProductId(item.getProductId());
        apply.setProductPic(item.getProductPic());
        apply.setProductName(item.getProductName());
        apply.setProductBrand(item.getProductBrand());
        apply.setProductAttr(item.getProductAttr());
        apply.setProductCount(item.getProductQuantity());
        apply.setProductPrice(item.getProductPrice());
        apply.setProductRealPrice(realPrice);
        apply.setReturnAmount(realPrice.multiply(BigDecimal.valueOf(item.getProductQuantity())));
        apply.setReturnName(order.getReceiverName());
        apply.setReturnPhone(order.getReceiverPhone());
        apply.setReason(param.getReason());
        apply.setDescription(param.getDescription());
        apply.setProofPics(param.getProofPics());
        apply.setCreateTime(new Date());
        apply.setStatus(0);
        returnApplyMapper.insertSelective(apply);
        return apply;
    }

    @Override
    public List<OmsOrderReturnApply> list(String orderSn, Integer pageSize, Integer pageNum) {
        PageHelper.startPage(pageNum, pageSize);
        return returnApplyDao.list(memberService.getCurrentMember().getId(), orderSn);
    }

    @Override
    public List<OmsOrderReturnApply> listActiveByOrderSns(List<String> orderSns) {
        if (orderSns == null || orderSns.isEmpty()) {
            return Collections.emptyList();
        }
        List<String> normalizedOrderSns = orderSns.stream()
                .filter(StringUtils::hasText)
                .distinct()
                .collect(Collectors.toList());
        if (normalizedOrderSns.isEmpty()) {
            return Collections.emptyList();
        }
        if (normalizedOrderSns.size() > 20) {
            Asserts.fail("单次最多查询20个订单的售后状态");
        }
        return returnApplyDao.listActiveByOrderSns(
                memberService.getCurrentMember().getId(), normalizedOrderSns);
    }

    @Override
    public OmsOrderReturnApply getItem(Long id) {
        OmsOrderReturnApply apply = returnApplyDao.getItem(memberService.getCurrentMember().getId(), id);
        if (apply == null) {
            Asserts.fail("售后申请不存在或不属于当前用户");
        }
        return apply;
    }
}
