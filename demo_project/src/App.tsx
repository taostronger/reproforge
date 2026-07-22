import { useState } from 'react';
import './App.css';

/**
 * ReproForge 被测商城 Demo —— 预埋 3 个 Bug（美化版，保留所有 data-testid + Bug 逻辑）：
 *   Bug1: 优惠总价在 apply 时只算一次，数量变化后不重新计算
 *   Bug2: 优惠码输入框 onChange 不清除旧错误提示
 *   Bug3: 删除商品后若曾 apply 优惠码，总价不归零
 * 所有交互元素带 data-testid，供 Playwright 稳定定位（勿改名）。
 */
interface CartItem { productId: number; qty: number; }
interface Product { id: number; name: string; price: number; desc: string; emoji: string; }

const PRODUCTS: Product[] = [
  { id: 1, name: '机械键盘', price: 100, desc: '客制化轴体 · 热插拔', emoji: '⌨️' },
  { id: 2, name: '无线鼠标', price: 80, desc: '静音点击 · 2.4G', emoji: '🖱️' },
  { id: 3, name: 'USB-C 数据线', price: 20, desc: '100W 快充 · 编织', emoji: '🔌' },
  { id: 4, name: '显示器支架', price: 150, desc: '人体工学 · 旋转', emoji: '🖥️' },
];

export default function App() {
  const [cart, setCart] = useState<CartItem[]>([{ productId: 1, qty: 1 }]);
  const [coupon, setCoupon] = useState('');
  const [couponApplied, setCouponApplied] = useState(false);
  const [totalAfterDiscount, setTotalAfterDiscount] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  const subtotal = cart.reduce((s, it) => {
    const p = PRODUCTS.find(x => x.id === it.productId)!;
    return s + p.price * it.qty;
  }, 0);

  // BUG1（buggy 版）: 优惠总价只在 apply 时算一次，改数量不重算 → total 不随 qty 变。
  //   演示 fixed 闭环：访问 ?fixed=1 时优惠总价随数量实时重算（subtotal*0.8），
  //   同一测试 buggy 失败（actual 80 ≠ 断言 160）、fixed 通过（actual 160）。
  const FIXED = typeof window !== 'undefined'
    && new URLSearchParams(window.location.search).get('fixed') === '1';
  const total = couponApplied
    ? (FIXED ? subtotal * 0.8 : (totalAfterDiscount !== null ? totalAfterDiscount : subtotal))
    : subtotal;

  const applyCoupon = () => {
    if (coupon.trim() === 'SALE20') {
      setCouponApplied(true);
      setTotalAfterDiscount(subtotal * 0.8); // 八折，仅此刻算一次
      // BUG2: 成功时也未清除旧错误提示（应 setErrorMsg('')）
    } else {
      setErrorMsg('优惠码无效');
    }
  };

  // BUG2: 重新输入时不清除错误提示（应 setErrorMsg('')）
  const onCouponChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setCoupon(e.target.value);
  };

  const setQty = (productId: number, qty: number) => {
    setCart(cart.map(it => it.productId === productId ? { ...it, qty: Math.max(0, qty) } : it));
  };

  const addToCart = (productId: number) => {
    const ex = cart.find(it => it.productId === productId);
    if (ex) setQty(productId, ex.qty + 1);
    else setCart([...cart, { productId, qty: 1 }]);
  };

  const removeItem = (productId: number) => {
    setCart(cart.filter(it => it.productId !== productId));
    // BUG3: cart 清空后若曾 apply 优惠，total 仍用旧 totalAfterDiscount，不归零
  };

  return (
    <div className="app">
      <header className="hdr">
        <div className="brand">⚙️ ForgeMall</div>
        <div className="slogan">DGX Spark 测试商城 · 预埋 Bug 演示</div>
        <button className="report-bug" onClick={() => window.open('http://localhost:7860', '_blank', 'noopener')}>
          🐞 Report Bug
        </button>
      </header>

      <section className="shelf">
        <h2 className="sec-title">货架</h2>
        <div className="grid">
          {PRODUCTS.map(p => (
            <div key={p.id} className="card">
              <div className="emoji">{p.emoji}</div>
              <div className="name">{p.name}</div>
              <div className="desc">{p.desc}</div>
              <div className="price">¥{p.price}</div>
              <button className="add" data-testid={`add-${p.id}`} onClick={() => addToCart(p.id)}>
                加入购物车
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="cart-sec">
        <h2 className="sec-title">购物车</h2>
        {cart.length === 0 && <div className="empty">购物车空了</div>}
        {cart.map(it => {
          const p = PRODUCTS.find(x => x.id === it.productId)!;
          return (
            <div key={it.productId} data-testid={`item-${it.productId}`} className="cart-item">
              <span className="ci-emoji">{p.emoji}</span>
              <span className="ci-name">{p.name}</span>
              <span className="ci-price">¥{p.price}</span>
              <span className="ci-x">×</span>
              <input
                data-testid={it.productId === 1 ? 'qty-input' : `qty-input-${it.productId}`}
                type="number" min={0} value={it.qty}
                onChange={e => setQty(it.productId, parseInt(e.target.value) || 0)}
                className="qty"
              />
              <button data-testid="remove-btn" onClick={() => removeItem(it.productId)} className="rm">删除</button>
            </div>
          );
        })}
      </section>

      <section className="coupon-sec">
        <input
          data-testid="coupon-input" value={coupon} onChange={onCouponChange}
          placeholder="优惠码（试 SALE20 八折）" className="coupon-input"
        />
        <button data-testid="apply-btn" onClick={applyCoupon} className="apply">应用</button>
        {errorMsg && <span data-testid="coupon-error" className="err">{errorMsg}</span>}
      </section>

      <section className="total-sec">
        <div className="subtotal">小计（不含优惠）<span>¥{subtotal}</span></div>
        <div className="total">总价 <span className="currency">¥</span><span data-testid="total-price">{total}</span></div>
      </section>
    </div>
  );
}
