package com.macro.mall.portal.service;

import com.macro.mall.portal.domain.OmsOrderReturnApplyParam;
import com.macro.mall.model.OmsOrderReturnApply;

import java.util.List;

/**
 * 前台订单退货管理Service
 * Created by macro on 2018/10/17.
 */
public interface OmsPortalOrderReturnApplyService {
    /**
     * 提交申请
     */
    OmsOrderReturnApply create(OmsOrderReturnApplyParam returnApply);

    List<OmsOrderReturnApply> list(String orderSn, Integer pageSize, Integer pageNum);

    OmsOrderReturnApply getItem(Long id);
}
