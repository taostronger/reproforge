import { useState } from 'react';

/**
 * ReproForge 被测商城 Demo —— 预埋 3 个 Bug：
 *   Bug1: 优惠总价在 apply 时只算一次，数量变化后不重新计算
 *   Bug2: 优惠码输入框 onChange 不清除旧错误提示
 *   Bug3: 删除商品后若曾 apply 优惠码，总价不归零
 * 所有交互元素带 data-testid，供 Playwright 稳定定位。
 */
interface CartItem { productId: number; qty: number; }
interface Product { id: number; name: string; price: number; }

const PRODUCTS: Product[] = [
  { id: 1, name: '商品A', price: 100 },
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

  // BUG1: 优惠总价只在 apply 时算一次；改数量不重算 → total 不随 qty 变
  const total = couponApplied && totalAfterDiscount !== null ? totalAfterDiscount : subtotal;

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

  const removeItem = (productId: number) => {
    setCart(cart.filter(it => it.productId !== productId));
  };

  // BUG3: cart 清空后若曾 apply 优惠，total 仍用旧 totalAfterDiscount，不归零
  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif', maxWidth: 480 }}>
      <h1>商城 Demo</h1>
      {cart.map(it => {
        const p = PRODUCTS.find(x => x.id === it.productId)!;
        return (
          <div key={it.productId} data-testid={`item-${it.productId}`} style={{ marginBottom: 12 }}>
            <span>{p.name} ¥{p.price} × </span>
            <input
              data-testid="qty-input"
              type="number"
              value={it.qty}
              onChange={e => setQty(it.productId, parseInt(e.target.value) || 0)}
              style={{ width: 60 }}
            />
            <button data-testid="remove-btn" onClick={() => removeItem(it.productId)} style={{ marginLeft: 8 }}>
              删除
            </button>
          </div>
        );
      })}

      <div style={{ marginTop: 16 }}>
        <input
          data-testid="coupon-input"
          value={coupon}
          onChange={onCouponChange}
          placeholder="优惠码 (试 SALE20)"
          style={{ width: 160 }}
        />
        <button data-testid="apply-btn" onClick={applyCoupon} style={{ marginLeft: 8 }}>
          应用
        </button>
        {errorMsg && (
          <span data-testid="coupon-error" style={{ color: 'red', marginLeft: 8 }}>{errorMsg}</span>
        )}
      </div>

      <h2>总价: ¥<span data-testid="total-price">{total}</span></h2>
      <p style={{ color: '#888', fontSize: 12 }}>小计(不含优惠): ¥{subtotal}</p>
    </div>
  );
}
