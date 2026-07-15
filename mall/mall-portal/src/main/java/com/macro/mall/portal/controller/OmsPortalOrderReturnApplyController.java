package com.macro.mall.portal.controller;

import com.macro.mall.common.api.CommonResult;
import com.macro.mall.common.api.CommonPage;
import com.macro.mall.model.OmsOrderReturnApply;
import com.macro.mall.portal.domain.OmsOrderReturnApplyParam;
import com.macro.mall.portal.service.OmsPortalOrderReturnApplyService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

import java.util.List;

/**
 * 退货申请管理Controller
 * Created by macro on 2018/10/17.
 */
@Controller
@Tag(name = "OmsPortalOrderReturnApplyController",description = "退货申请管理")
@RequestMapping("/returnApply")
public class OmsPortalOrderReturnApplyController {
    @Autowired
    private OmsPortalOrderReturnApplyService returnApplyService;

    @Operation(summary = "申请退货")
    @RequestMapping(value = "/create", method = RequestMethod.POST)
    @ResponseBody
    public CommonResult<OmsOrderReturnApply> create(@RequestBody OmsOrderReturnApplyParam returnApply) {
        return CommonResult.success(returnApplyService.create(returnApply));
    }

    @Operation(summary = "查询当前用户售后申请")
    @RequestMapping(value = "/list", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<CommonPage<OmsOrderReturnApply>> list(
            @RequestParam(value = "orderSn", required = false) String orderSn,
            @RequestParam(value = "pageSize", defaultValue = "10") Integer pageSize,
            @RequestParam(value = "pageNum", defaultValue = "1") Integer pageNum) {
        List<OmsOrderReturnApply> list = returnApplyService.list(orderSn, pageSize, pageNum);
        return CommonResult.success(CommonPage.restPage(list));
    }

    @Operation(summary = "查询当前用户售后申请详情")
    @RequestMapping(value = "/{id}", method = RequestMethod.GET)
    @ResponseBody
    public CommonResult<OmsOrderReturnApply> getItem(@PathVariable Long id) {
        return CommonResult.success(returnApplyService.getItem(id));
    }
}
