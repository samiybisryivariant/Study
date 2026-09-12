import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid")
pd.set_option("display.width", 200)

df = pd.read_csv("support_ticket_risk_features_raw.csv", parse_dates=["ref_date", "registration_date"])
print("raw shape:", df.shape)

assert df["remove_from_cart_events_30d"].sum() == 0
df = df.drop(columns=["remove_from_cart_events_30d"])

for col in ["session_count_30d", "total_events_30d"]:
    q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
    upper = q3 + 1.5 * (q3 - q1)
    n_out = (df[col] > upper).sum()
    df[col + "_capped"] = df[col].clip(upper=upper)
    print(f"winsorized {col}: upper={upper:.1f}, capped {n_out} rows ({n_out/len(df)*100:.1f}%)")

na_cols = ["avg_session_duration_min_30d", "checkout_conversion_rate_30d",
           "cancelled_refunded_rate_30d", "notification_open_rate_30d", "avg_review_rating_30d"]
print("\nNaN пропорции (оставлены как есть):")
print((df[na_cols].isna().mean() * 100).round(1))

df.to_csv("support_ticket_risk_features_clean.csv", index=False, encoding="utf-8-sig")
df_xlsx = df.copy()
for c in ["ref_date", "registration_date"]:
    df_xlsx[c] = df_xlsx[c].dt.tz_localize(None)
df_xlsx.to_excel("support_ticket_risk_features_clean.xlsx", index=False)

print("\n=== баланс классов (has_ticket) ===")
print(df["has_ticket"].value_counts())
print(df["has_ticket"].value_counts(normalize=True))

print("\n=== is_thin_history по классам (пользователи без активности в окне) ===")
print(pd.crosstab(df["has_ticket"], df["is_thin_history"], normalize="index"))

print("\n=== корреляции с has_ticket ===")
target = df["has_ticket"].astype(int)
num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
num_cols = [c for c in num_cols if c not in ("user_id",)]
corr = df[num_cols].corrwith(target).drop("has_ticket", errors="ignore").sort_values(key=abs, ascending=False)
print(corr)

print("\n--- H1: payment_failed_30d>0 -> ticket rate ---")
g = df.assign(had_fail=df["payment_failed_30d"] > 0).groupby("had_fail")["has_ticket"].mean()
print(g)

print("\n--- H2: cancelled_refunded_rate_30d (где определено) по has_ticket ---")
sub = df.dropna(subset=["cancelled_refunded_rate_30d"])
print(sub.groupby("has_ticket")["cancelled_refunded_rate_30d"].agg(["mean", "count"]))

print("\n--- H3: checkout_conversion_rate_30d (где определено) по has_ticket ---")
sub = df.dropna(subset=["checkout_conversion_rate_30d"])
print(sub.groupby("has_ticket")["checkout_conversion_rate_30d"].agg(["mean", "count"]))

print("\n--- H4: notification_open_rate_30d (где определено) по has_ticket ---")
sub = df.dropna(subset=["notification_open_rate_30d"])
print(sub.groupby("has_ticket")["notification_open_rate_30d"].agg(["mean", "count"]))

palette = {False: "#4C78A8", True: "#E45756"}

fig, ax = plt.subplots(figsize=(6, 4.5))
had_fail = df.assign(had_fail=np.where(df["payment_failed_30d"] > 0, "был отказ оплаты", "отказов не было"))
rates = had_fail.groupby("had_fail")["has_ticket"].mean().reindex(["отказов не было", "был отказ оплаты"])
bars = ax.bar(rates.index, rates.values * 100, color=["#4C78A8", "#E45756"])
ax.set_ylabel("Доля пользователей с обращением в поддержку, %")
ax.set_title("Риск обращения в поддержку и отказ оплаты\nза 30 дней до среза")
for b, v in zip(bars, rates.values):
    ax.text(b.get_x() + b.get_width()/2, v*100 + 0.3, f"{v*100:.1f}%", ha="center")
fig.tight_layout()
fig.savefig("1_bar_ticket_rate_by_payment_failed.png", dpi=150)
plt.close(fig)

fig, ax = plt.subplots(figsize=(6.5, 4.5))
sub = df.dropna(subset=["notification_open_rate_30d"])
sns.histplot(data=sub, x="notification_open_rate_30d", hue="has_ticket", stat="density",
             common_norm=False, bins=20, palette=palette, ax=ax, alpha=0.55, element="step")
ax.set_xlabel("Доля открытых push-уведомлений за 30 дней")
ax.set_ylabel("Плотность")
ax.set_title("Вовлечённость (открытие уведомлений)\nу обратившихся и не обратившихся в поддержку")
fig.tight_layout()
fig.savefig("2_hist_notification_open_rate.png", dpi=150)
plt.close(fig)

fig, ax = plt.subplots(figsize=(6.5, 5))
sub = df.dropna(subset=["checkout_conversion_rate_30d"]).copy()
rng = np.random.default_rng(42)
sub["session_count_30d_jitter"] = sub["session_count_30d_capped"] + rng.uniform(-0.18, 0.18, len(sub))
sns.scatterplot(data=sub, x="session_count_30d_jitter", y="checkout_conversion_rate_30d",
                 hue="has_ticket", palette=palette, alpha=0.5, s=35, ax=ax)
ax.set_xlabel("Число сессий за 30 дней (winsorized)")
ax.set_ylabel("Конверсия чекаута в покупку за 30 дней")
ax.set_title("Активность в приложении и конверсия чекаута")
fig.tight_layout()
fig.savefig("3_scatter_conversion_vs_sessions.png", dpi=150)
plt.close(fig)

key_cols = ["has_ticket", "payment_failed_30d", "cancelled_refunded_rate_30d",
            "checkout_conversion_rate_30d", "notification_open_rate_30d",
            "session_count_30d_capped", "total_events_30d_capped"]
corr_matrix = df[key_cols].astype(float).corr()
fig, ax = plt.subplots(figsize=(7.5, 6))
sns.heatmap(corr_matrix, annot=True, fmt=".2f", cmap="RdBu_r", center=0, vmin=-0.3, vmax=0.3, ax=ax)
ax.set_title("Корреляции ключевых признаков риска\nобращения в поддержку")
fig.tight_layout()
fig.savefig("4_heatmap_correlation.png", dpi=150)
plt.close(fig)

print("\nГотово: графики и очищенные файлы сохранены.")
