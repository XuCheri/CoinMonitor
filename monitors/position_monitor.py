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
                 history_days: int = 1, **kwargs):
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
    
    async def get_position_history(self, days: int = 1) -> List[Dict[str, Any]]:
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
                             position_history: Optional[List[Dict[str, Any]]] = None,
                             actual_days: Union[int, None] = None) -> List[str]:
        """格式化持仓报告，返回多个部分用于分段推送"""
        parts = []
        
        # 第一部分：标题 + 期货持仓 + 现货余额
        part1 = "📊 <b>币安账户持仓报告</b>\n\n"
        
        # 期货持仓
        futures_positions = current_positions.get('futures', [])
        if futures_positions:
            part1 += "🎯 <b>期货持仓</b>\n"
            metrics = self.calculate_position_metrics(futures_positions)
            
            part1 += f"总持仓数: {metrics['total_positions']}\n"
            part1 += f"多仓: {metrics['long_positions']} | 空仓: {metrics['short_positions']}\n"
            part1 += f"平均杠杆: {metrics['avg_leverage']:.1f}x\n"
            part1 += f"未实现盈亏: {metrics['total_unrealized_pnl']:.2f} USDT\n\n"
            
            for pos in futures_positions:
                pnl_percent = (pos['unrealized_pnl'] / (pos['size'] * pos['entry_price'])) * 100
                part1 += f"• {pos['symbol']} {pos['side']}\n"
                part1 += f"  数量: {pos['size']:.4f} | 杠杆: {pos['leverage']}x\n"
                part1 += f"  开仓价: {pos['entry_price']:.4f} | 标记价: {pos['mark_price']:.4f}\n"
                part1 += f"  盈亏: {pos['unrealized_pnl']:.2f} USDT ({pnl_percent:+.2f}%)\n\n"
        else:
            part1 += "🎯 <b>期货持仓</b>: 无持仓\n\n"
        
        # 现货余额
        spot_balances = current_positions.get('spot', [])
        if spot_balances:
            part1 += "💰 <b>现货余额</b>\n"
            total_spot_value = 0
            
            for balance in spot_balances:
                if balance['asset'] != 'USDT':
                    part1 += f"• {balance['asset']}: {balance['total']:.6f}\n"
                else:
                    part1 += f"• {balance['asset']}: {balance['total']:.2f}\n"
                    total_spot_value += balance['total']
            
            part1 += f"\n现货总价值: {total_spot_value:.2f} USDT\n\n"
        
        part1 += f"⏰ 报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        parts.append(part1)
        
        # 第二部分：历史仓位盈亏详情（如果有历史数据且启用，自动分割）
        if position_history and self.include_history:
            MAX_LEN = 3500
            days_to_show = actual_days if actual_days is not None else self.history_days
            if days_to_show == 1:
                part2_header = "📈 <b>今日持仓盈亏详情</b>\n\n"
            else:
                part2_header = f"📈 <b>历史持仓盈亏详情（近{days_to_show}天）</b>\n\n"

            from collections import defaultdict, deque
            symbol_long_queue = defaultdict(deque)
            symbol_short_queue = defaultdict(deque)
            realized_pnl_records = []
            sorted_trades = sorted(position_history, key=lambda x: x['time'])

            for trade in sorted_trades:
                symbol = trade['symbol']
                side = trade['side']
                qty = trade['quantity']
                price = trade['price']
                time_str = trade['time']

                if side == 'BUY':
                    remaining_qty = qty
                    while remaining_qty > 0 and symbol_short_queue[symbol]:
                        pos = symbol_short_queue[symbol][0]
                        close_qty = min(remaining_qty, pos['quantity'])
                        pnl = (pos['price'] - price) * close_qty
                        realized_pnl_records.append({
                            'symbol': symbol,
                            'side': 'SHORT',
                            'open_price': pos['price'],
                            'close_price': price,
                            'quantity': close_qty,
                            'pnl': pnl,
                            'time': time_str
                        })
                        pos['quantity'] -= close_qty
                        remaining_qty -= close_qty
                        if pos['quantity'] == 0:
                            symbol_short_queue[symbol].popleft()
                    if remaining_qty > 0:
                        symbol_long_queue[symbol].append({'quantity': remaining_qty, 'price': price, 'time': time_str})
                elif side == 'SELL':
                    remaining_qty = qty
                    while remaining_qty > 0 and symbol_long_queue[symbol]:
                        pos = symbol_long_queue[symbol][0]
                        close_qty = min(remaining_qty, pos['quantity'])
                        pnl = (price - pos['price']) * close_qty
                        realized_pnl_records.append({
                            'symbol': symbol,
                            'side': 'LONG',
                            'open_price': pos['price'],
                            'close_price': price,
                            'quantity': close_qty,
                            'pnl': pnl,
                            'time': time_str
                        })
                        pos['quantity'] -= close_qty
                        remaining_qty -= close_qty
                        if pos['quantity'] == 0:
                            symbol_long_queue[symbol].popleft()
                    if remaining_qty > 0:
                        symbol_short_queue[symbol].append({'quantity': remaining_qty, 'price': price, 'time': time_str})

            # 合并每个symbol每个方向的所有平仓明细
            symbol_side_stats = defaultdict(lambda: {'total_qty': 0.0, 'open_sum': 0.0, 'close_sum': 0.0, 'pnl': 0.0, 'last_time': ''})
            for record in realized_pnl_records:
                key = (record['symbol'], record['side'])
                q = float(record['quantity'])
                open_p = float(record['open_price'])
                close_p = float(record['close_price'])
                pnl = float(record['pnl'])
                symbol_side_stats[key]['total_qty'] = float(symbol_side_stats[key]['total_qty']) + q
                symbol_side_stats[key]['open_sum'] = float(symbol_side_stats[key]['open_sum']) + open_p * q
                symbol_side_stats[key]['close_sum'] = float(symbol_side_stats[key]['close_sum']) + close_p * q
                symbol_side_stats[key]['pnl'] = float(symbol_side_stats[key]['pnl']) + pnl
                if record['time'] > symbol_side_stats[key]['last_time']:
                    symbol_side_stats[key]['last_time'] = record['time']

            # 生成报告
            events = []
            for (symbol, side), stats in symbol_side_stats.items():
                total_qty = float(stats['total_qty'])
                if total_qty == 0:
                    continue
                avg_open = float(stats['open_sum']) / total_qty if total_qty else 0
                avg_close = float(stats['close_sum']) / total_qty if total_qty else 0
                total_pnl = float(stats['pnl'])
                last_time = stats['last_time'] or ''
                events.append({
                    'symbol': symbol,
                    'side': side,
                    'qty': total_qty,
                    'avg_open': avg_open,
                    'avg_close': avg_close,
                    'pnl': total_pnl,
                    'time': last_time
                })
            events.sort(key=lambda x: x['time'], reverse=True)

            buf = part2_header
            for e in events:
                if e['pnl'] >= 0:
                    pnl_str = f"<b><code>+{e['pnl']:.2f} USDT</code></b> 🟢"
                else:
                    pnl_str = f"<b><code>{e['pnl']:.2f} USDT</code></b> 🔴"
                event_str = (f"• <b>{e['symbol']}</b> <b>{e['side']}</b>\n"
                             f"  数量: <code>{e['qty']:.4f}</code>\n"
                             f"  开均价: <code>{e['avg_open']:.4f}</code>  平均价: <code>{e['avg_close']:.4f}</code>\n"
                             f"  盈亏: {pnl_str}\n"
                             f"  时间: <code>{e['time'][:16].replace('T', ' ')}</code>\n")
                if len(buf) + len(event_str) > MAX_LEN:
                    parts.append(buf)
                    buf = part2_header + event_str
                else:
                    buf += event_str
            if buf != part2_header:
                parts.append(buf)
        
        return parts
    
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
            parts = self.format_position_report(current_positions, position_history, actual_days=self.history_days)
            for part in parts:
                await self.send_message(part, parse_mode="HTML")
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
            parts = self.format_position_report(current_positions, position_history, actual_days=days)
            return "\n\n".join(parts)
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