import asyncio
import aiohttp
import hmac
import hashlib
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urlencode
import pandas as pd
import numpy as np
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
except ImportError:
    Client = None
    BinanceAPIException = Exception
from .base_monitor import BaseMonitor
from utils.logger import log_info, log_error


class PositionMonitor(BaseMonitor):
    """
    币安账户持仓监控器
    功能：
    1. 获取当前持仓信息
    2. 获取历史仓位记录
    3. 生成持仓分析报告
    4. 定期推送持仓状态
    """
    
    def __init__(self, bot, chat_id: int, topic_id: int, proxy_url: Optional[str] = None, 
                 interval: int = 3600, api_key: str = "", api_secret: str = "", 
                 testnet: bool = False, auto_report: bool = True, 
                 report_time: str = "09:00", include_history: bool = True, 
                 history_days: int = 7, **kwargs):
        super().__init__(bot, chat_id, topic_id, proxy_url, interval, **kwargs)
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.auto_report = auto_report
        self.report_time = report_time
        self.include_history = include_history
        self.history_days = history_days
        
        # 初始化币安客户端
        self.binance_client: Optional[Client] = None
        self._init_binance_client()
        
        # 持仓数据缓存
        self.current_positions: Dict[str, Any] = {}
        self.position_history: List[Dict[str, Any]] = []
        
    def _init_binance_client(self):
        """初始化币安API客户端"""
        if Client is None:
            log_error("❌ python-binance 库未安装")
            return
            
        try:
            if self.testnet:
                self.binance_client = Client(self.api_key, self.api_secret, testnet=True)
            else:
                self.binance_client = Client(self.api_key, self.api_secret)
            log_info("✅ 币安API客户端初始化成功")
        except Exception as e:
            log_error(f"❌ 币安API客户端初始化失败: {e}")
            self.binance_client = None
    
    def _generate_signature(self, params: dict) -> str:
        """生成API签名"""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _make_signed_request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """发送带签名的API请求"""
        if not self.binance_client:
            raise Exception("币安API客户端未初始化")
        
        try:
            if endpoint.startswith('/fapi/'):
                # 期货API
                return self.binance_client.futures_account_trades()
            elif endpoint.startswith('/api/v3/'):
                # 现货API
                return self.binance_client.get_account()
            else:
                raise Exception(f"不支持的API端点: {endpoint}")
        except BinanceAPIException as e:
            log_error(f"币安API错误: {e}")
            raise
        except Exception as e:
            log_error(f"API请求错误: {e}")
            raise
    
    async def get_current_positions(self) -> Dict[str, Any]:
        """获取当前持仓信息"""
        if not self.binance_client:
            raise Exception("币安API客户端未初始化")
            
        try:
            # 获取期货账户信息
            futures_account = self.binance_client.futures_account()
            positions = []
            
            # 先筛选有持仓的symbol
            held_positions = [p for p in futures_account['positions'] if float(p['positionAmt']) != 0]
            held_symbols = [p['symbol'] for p in held_positions]
            mark_price_map = {}
            if held_symbols:
                # 获取所有有持仓symbol的markPrice
                all_position_info = self.binance_client.futures_position_information()
                for info in all_position_info:
                    if info['symbol'] in held_symbols:
                        mark_price_map[info['symbol']] = float(info['markPrice'])
            
            for position in held_positions:
                symbol = position['symbol']
                mark_price = mark_price_map.get(symbol, float(position['entryPrice']))
                positions.append({
                    'symbol': symbol,
                    'side': 'LONG' if float(position['positionAmt']) > 0 else 'SHORT',
                    'size': abs(float(position['positionAmt'])),
                    'entry_price': float(position['entryPrice']),
                    'mark_price': mark_price,
                    'unrealized_pnl': float(position['unrealizedProfit']),
                    'margin_type': position.get('marginType', ''),
                    'isolated_margin': float(position.get('isolatedWallet', 0)),
                    'leverage': int(position['leverage'])
                })
            
            # 获取现货账户信息
            spot_account = self.binance_client.get_account()
            spot_balances = []
            
            for balance in spot_account['balances']:
                if float(balance['free']) > 0 or float(balance['locked']) > 0:
                    spot_balances.append({
                        'asset': balance['asset'],
                        'free': float(balance['free']),
                        'locked': float(balance['locked']),
                        'total': float(balance['free']) + float(balance['locked'])
                    })
            
            return {
                'futures': positions,
                'spot': spot_balances,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            log_error(f"获取当前持仓失败: {e}")
            raise
    
    async def get_position_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取历史仓位记录"""
        if not self.binance_client:
            raise Exception("币安API客户端未初始化")
            
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # 获取期货交易历史
            futures_trades = self.binance_client.futures_account_trades()
            
            # 过滤指定时间范围内的交易
            filtered_trades = []
            for trade in futures_trades:
                trade_time = datetime.fromtimestamp(trade['time'] / 1000)
                if start_time <= trade_time <= end_time:
                    filtered_trades.append({
                        'symbol': trade['symbol'],
                        'side': trade['side'],
                        'quantity': float(trade['qty']),
                        'price': float(trade['price']),
                        'realized_pnl': float(trade['realizedPnl']),
                        'commission': float(trade['commission']),
                        'time': trade_time.isoformat(),
                        'type': 'futures'
                    })
            
            return filtered_trades
            
        except Exception as e:
            log_error(f"获取历史仓位失败: {e}")
            raise
    
    def calculate_position_metrics(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算持仓指标"""
        if not positions:
            return {
                'total_positions': 0,
                'total_unrealized_pnl': 0,
                'long_positions': 0,
                'short_positions': 0,
                'avg_leverage': 0
            }
        
        total_unrealized_pnl = sum(pos['unrealized_pnl'] for pos in positions)
        long_positions = len([pos for pos in positions if pos['side'] == 'LONG'])
        short_positions = len([pos for pos in positions if pos['side'] == 'SHORT'])
        avg_leverage = np.mean([pos['leverage'] for pos in positions])
        
        return {
            'total_positions': len(positions),
            'total_unrealized_pnl': total_unrealized_pnl,
            'long_positions': long_positions,
            'short_positions': short_positions,
            'avg_leverage': avg_leverage
        }
    
    def format_position_report(self, current_positions: Dict[str, Any], 
                             position_history: Optional[List[Dict[str, Any]]] = None) -> str:
        """格式化持仓报告"""
        report = "📊 <b>币安账户持仓报告</b>\n\n"
        
        # 期货持仓
        futures_positions = current_positions.get('futures', [])
        if futures_positions:
            report += "🎯 <b>期货持仓</b>\n"
            metrics = self.calculate_position_metrics(futures_positions)
            
            report += f"总持仓数: {metrics['total_positions']}\n"
            report += f"多仓: {metrics['long_positions']} | 空仓: {metrics['short_positions']}\n"
            report += f"平均杠杆: {metrics['avg_leverage']:.1f}x\n"
            report += f"未实现盈亏: {metrics['total_unrealized_pnl']:.2f} USDT\n\n"
            
            for pos in futures_positions:
                pnl_percent = (pos['unrealized_pnl'] / (pos['size'] * pos['entry_price'])) * 100
                report += f"• {pos['symbol']} {pos['side']}\n"
                report += f"  数量: {pos['size']:.4f} | 杠杆: {pos['leverage']}x\n"
                report += f"  开仓价: {pos['entry_price']:.4f} | 标记价: {pos['mark_price']:.4f}\n"
                report += f"  盈亏: {pos['unrealized_pnl']:.2f} USDT ({pnl_percent:+.2f}%)\n\n"
        else:
            report += "🎯 <b>期货持仓</b>: 无持仓\n\n"
        
        # 现货余额
        spot_balances = current_positions.get('spot', [])
        if spot_balances:
            report += "💰 <b>现货余额</b>\n"
            total_spot_value = 0
            
            for balance in spot_balances:
                if balance['asset'] != 'USDT':
                    # 这里可以添加获取实时价格来计算USDT价值
                    report += f"• {balance['asset']}: {balance['total']:.6f}\n"
                else:
                    report += f"• {balance['asset']}: {balance['total']:.2f}\n"
                    total_spot_value += balance['total']
            
            report += f"\n现货总价值: {total_spot_value:.2f} USDT\n\n"
        
        # 历史交易记录
        if position_history and self.include_history:
            report += "📈 <b>最近交易记录</b>\n"
            recent_trades = position_history[-10:]  # 最近10笔交易
            
            for trade in recent_trades:
                report += f"• {trade['symbol']} {trade['side']} {trade['quantity']:.4f} @ {trade['price']:.4f}\n"
                report += f"  盈亏: {trade['realized_pnl']:.2f} USDT | 时间: {trade['time'][:19]}\n\n"
        
        report += f"⏰ 报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return report
    
    async def check(self):
        """执行持仓检查"""
        try:
            # 获取当前持仓
            current_positions = await self.get_current_positions()
            self.current_positions = current_positions
            
            # 获取历史仓位（如果需要）
            position_history: Optional[List[Dict[str, Any]]] = None
            if self.include_history:
                position_history = await self.get_position_history(self.history_days)
                self.position_history = position_history
            
            # 生成报告
            report = self.format_position_report(current_positions, position_history)
            
            # 发送报告
            await self.send_message(report, parse_mode="HTML")
            
            log_info("✅ 持仓报告已发送")
            
        except Exception as e:
            log_error(f"❌ 持仓检查失败: {e}")
            error_msg = f"<b>持仓监控异常</b>\n<pre>{str(e)}</pre>"
            await self.send_message(error_msg, parse_mode="HTML")
    
    def get_status(self) -> str:
        """返回监控器状态"""
        status = f"📊 <b>持仓监控器状态</b>\n\n"
        status += f"状态: {'运行中' if self._running else '已停止'}\n"
        status += f"检查间隔: {self.interval}秒\n"
        status += f"自动报告: {'开启' if self.auto_report else '关闭'}\n"
        status += f"报告时间: {self.report_time}\n"
        status += f"包含历史: {'是' if self.include_history else '否'}\n"
        status += f"历史天数: {self.history_days}天\n"
        status += f"API状态: {'正常' if self.binance_client else '异常'}"
        return status
    
    async def get_manual_report(self, history_days: Optional[int] = None) -> str:
        """手动获取持仓报告"""
        try:
            current_positions = await self.get_current_positions()
            # 使用传入的天数，如果没有传入则使用默认设置
            days = history_days if history_days is not None else self.history_days
            position_history = await self.get_position_history(days) if self.include_history else None
            return self.format_position_report(current_positions, position_history)
        except Exception as e:
            return f"❌ 获取持仓报告失败: {str(e)}"
    
    def update_config(self, key: str, value: str) -> str:
        """更新配置"""
        if key in ['auto_report', 'include_history']:
            # 布尔值转换
            if value.lower() in ['true', '1', 'yes', 'on']:
                bool_value = True
            elif value.lower() in ['false', '0', 'no', 'off']:
                bool_value = False
            else:
                return f"❌ 无效的布尔值: {value}"
            
            setattr(self, key, bool_value)
            return f"✅ <b>{self.monitor_name}</b> 的配置 <code>{key}</code> 已更新为 <code>{bool_value}</code>。"
        
        return super().update_config(key, value) 