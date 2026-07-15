package com.macro.mall.portal.dao;

import com.macro.mall.model.OmsOrderReturnApply;
import org.apache.ibatis.annotations.Param;

import java.util.List;

public interface OmsPortalOrderReturnApplyDao {
    OmsOrderReturnApply getByIdempotencyKey(@Param("memberId") Long memberId,
                                             @Param("idempotencyKey") String idempotencyKey);

    List<OmsOrderReturnApply> list(@Param("memberId") Long memberId,
                                   @Param("orderSn") String orderSn);

    OmsOrderReturnApply getItem(@Param("memberId") Long memberId, @Param("id") Long id);
}
