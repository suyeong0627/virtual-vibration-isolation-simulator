import streamlit as st
import numpy as np
import time
from plotly.subplots import make_subplots
import plotly.graph_objects as go

st.set_page_config(page_title="가상 능동 진동 저감 시뮬레이터", layout="wide")
st.title("🖥️ 가상 능동 진동 저감 시뮬레이터 (PBC + 노치필터 + 지연보상)")
st.caption("실제 하드웨어 없이, 물리 모델로 진동/공진/통신지연까지 전부 가상으로 재현합니다.")

# =========================================================
# 핵심 물리 시뮬레이션 엔진 (제너레이터)
# =========================================================
def run_generator(control_on, notch_on, delay_ms, lead_on,
                   impulse_amp, ambient_amp, m, k, c_damp, Kv,
                   sim_seconds, dt=0.005):

    fs = 1.0 / dt
    f0 = 13.5
    Qf = 3.0
    w0 = 2*np.pi*f0/fs
    alpha = np.sin(w0)/(2*Qf)
    b0, b1, b2 = 1.0, -2*np.cos(w0), 1.0
    a0, a1, a2 = 1+alpha, -2*np.cos(w0), 1-alpha
    b0, b1, b2, a1, a2 = b0/a0, b1/a0, b2/a0, a1/a0, a2/a0

    x1 = x2 = y1 = y2 = 0.0
    z = 0.0
    v = 0.0
    p_sensor_hist = []
    delay_steps = int(round(delay_ms/1000.0/dt))
    n_steps = int(sim_seconds/dt)

    DIVERGE_LIMIT = 0.3

    for i in range(n_steps):
        t = i*dt
        old_v = v

        raw_x = old_v
        if notch_on:
            filtered_v = b0*raw_x + b1*x1 + b2*x2 - a1*y1 - a2*y2
        else:
            filtered_v = raw_x
        x2, x1 = x1, raw_x
        y2, y1 = y1, filtered_v

        p_sensor = m*filtered_v
        p_sensor_hist.append(p_sensor)

        idx_delayed = i - delay_steps
        p_delayed = p_sensor_hist[idx_delayed] if idx_delayed >= 0 else 0.0

        if lead_on and idx_delayed-1 >= 0:
            p_prev = p_sensor_hist[idx_delayed-1]
            deriv_est = (p_delayed - p_prev)/dt
            p_used = p_delayed + (delay_ms/1000.0)*deriv_est
        else:
            p_used = p_delayed

        F_c = -Kv*(p_used/m) if control_on else 0.0

        disturb = impulse_amp if 0.3 <= t < 0.38 else 0.0
        disturb += ambient_amp*np.sin(2*np.pi*13.5*t)

        a_acc = (disturb - c_damp*old_v - k*z + F_c)/m
        v = old_v + a_acc*dt
        z = z + v*dt

        p_actual = m*v
        H_new = (p_actual**2)/(2*m) + 0.5*k*z**2

        if abs(z) > DIVERGE_LIMIT or not np.isfinite(z):
            yield {"t": t, "z": float(np.sign(z) * DIVERGE_LIMIT if z != 0 else DIVERGE_LIMIT),
                   "v_raw": old_v, "v_filt": filtered_v,
                   "p": p_actual, "p_used": p_used, "H": H_new, "exploded": True}
            return

        yield {"t": t, "z": z, "v_raw": old_v, "v_filt": filtered_v,
               "p": p_actual, "p_used": p_used, "H": H_new, "exploded": False}

# =========================================================
# 사이드바
# =========================================================
st.sidebar.header("⚙️ 시스템 파라미터")
m = st.sidebar.slider("질량 m (kg)", 0.1, 2.0, 0.5, 0.1)
k = st.sidebar.slider("스프링 상수 k (N/m)", 100, 2000, 800, 50)
c_damp = st.sidebar.slider("기계적 감쇠 c", 0.0, 3.0, 0.1, 0.1)

st.sidebar.header("🎛 제어기 튜닝 (PBC)")
control_on = st.sidebar.checkbox("능동 제어 ON", value=True)
Kv = st.sidebar.slider("제어 게인 Kv", 0.0, 25.0, 15.0, 0.5)

st.sidebar.header("🧪 신호처리 고도화")
notch_on = st.sidebar.checkbox("🎚️ 13.5Hz 노치 필터 적용 (기구 공진 제거)", value=False)
delay_ms = st.sidebar.slider("📡 통신 지연 (ms)", 0, 50, 20, 5)
st.sidebar.caption("💡 13.5Hz 공진의 반주기(약 37ms)에 가까울수록 발산이 극적으로 나타납니다.")
lead_on = st.sidebar.checkbox("🧭 위상 리드 보상기 적용 (지연 보상)", value=False)

st.sidebar.header("🌊 외란 설정")
ambient_amp = st.sidebar.slider("바닥 울림 세기", 0.0, 1.0, 0.3, 0.05)
impulse_choice = st.sidebar.radio("충격 세기", ["약하게 두드리기", "세게 두드리기"], index=1)
impulse_amp = 8.0 if impulse_choice == "약하게 두드리기" else 25.0

sim_seconds = st.sidebar.slider("시뮬레이션 길이 (초)", 2, 10, 10, 1)

run_btn = st.button("▶️ 두드리고 시뮬레이션 시작", type="primary", use_container_width=True)

main_ph = st.empty()
metric_ph = st.empty()
warn_ph = st.empty()

# =========================================================
# 메인 애니메이션 렌더 함수 (★ key로 중복 ID 방지)
# =========================================================
def render_main(hist, violation_count, step=0):
    z_mm = hist["z"][-1]*1000
    scale = 15
    desk_y = 0.3 + (z_mm*scale)/1000
    t_hist = hist["t"]

    fig = make_subplots(rows=3, cols=2, subplot_titles=(
        "책상 흔들림", "변위 시계열(mm)",
        "위상 공간 (z,p)", "에너지(해밀토니안)",
        "속도 신호: 필터 적용 전/후", "제어 신호: 실제 vs 사용된 값"
    ))

    fig.add_shape(type="rect", x0=-1, x1=1, y0=desk_y, y1=desk_y+0.15,
                  fillcolor="saddlebrown", line_width=0, row=1, col=1)
    fig.add_shape(type="line", x0=-0.8, x1=-0.8, y0=0, y1=desk_y,
                  line=dict(color="gray", width=6), row=1, col=1)
    fig.add_shape(type="line", x0=0.8, x1=0.8, y0=0, y1=desk_y,
                  line=dict(color="gray", width=6), row=1, col=1)
    fig.update_xaxes(range=[-1.5, 1.5], visible=False, row=1, col=1)
    fig.update_yaxes(range=[-0.1, 1.0], visible=False, row=1, col=1)

    fig.add_trace(go.Scatter(x=t_hist, y=np.array(hist["z"])*1000,
                  line=dict(color='blue' if control_on else 'red'), showlegend=False), row=1, col=2)

    fig.add_trace(go.Scatter(x=np.array(hist["z"])*1000, y=hist["p"],
                  line=dict(color='purple'), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=[0], y=[0], mode='markers',
                  marker=dict(color='black', size=10), showlegend=False), row=2, col=1)

    fig.add_trace(go.Scatter(x=t_hist, y=hist["H"],
                  line=dict(color='green'), showlegend=False), row=2, col=2)

    fig.add_trace(go.Scatter(x=t_hist, y=hist["v_raw"],
                  line=dict(color='lightgray'), name='필터 전(Raw)'), row=3, col=1)
    fig.add_trace(go.Scatter(x=t_hist, y=hist["v_filt"],
                  line=dict(color='orange'), name='필터 후'), row=3, col=1)

    fig.add_trace(go.Scatter(x=t_hist, y=hist["p"],
                  line=dict(color='lightgray'), name='실제 p'), row=3, col=2)
    fig.add_trace(go.Scatter(x=t_hist, y=hist["p_used"],
                  line=dict(color='crimson'), name='제어 사용 p(지연/보상)'), row=3, col=2)

    fig.update_layout(height=900, margin=dict(l=10, r=10, t=40, b=10),
                       legend=dict(orientation="h"))

    # ★ [점검#1] 루프 안에서 반복 호출되므로 step 기반 동적 key 필수
    main_ph.plotly_chart(fig, use_container_width=True, key=f"main_chart_{step}")

    rms_now = np.sqrt(np.mean(np.array(hist["z"])**2))
    viol_pct = (violation_count/max(len(hist["H"]), 1))*100
    metric_ph.markdown(
        f"**현재 변위:** {z_mm:.3f} mm &nbsp;|&nbsp; "
        f"**RMS 변위:** {rms_now*1000:.3f} mm &nbsp;|&nbsp; "
        f"**에너지 불안정 비율:** {viol_pct:.2f}%"
    )

# =========================================================
# 메인 실행 루프
# =========================================================
if run_btn:
    hist = {k_: [] for k_ in ["t", "z", "v_raw", "v_filt", "p", "p_used", "H"]}
    violation_count = 0

    gen = run_generator(control_on, notch_on, delay_ms, lead_on,
                         impulse_amp, ambient_amp, m, k, c_damp, Kv, sim_seconds)

    exploded = False
    last_i = 0
    for i, state in enumerate(gen):
        last_i = i
        exploded = state.get("exploded", False)
        for key in ["t", "z", "v_raw", "v_filt", "p", "p_used", "H"]:
            hist[key].append(state[key])
        if len(hist["H"]) > 1 and hist["H"][-1] > hist["H"][-2] + 1e-6:
            violation_count += 1
        if i % 15 == 0 or exploded:
            render_main(hist, violation_count, step=i)  # ★ 매번 다른 i
            time.sleep(0.01)
        if exploded:
            break

    # ★ [점검#2] 마지막 강제 렌더는 루프의 마지막 i와 절대 겹치지 않을 값 사용
    render_main(hist, violation_count, step=last_i + 1)

    if exploded:
        warn_ph.error("💥 **시스템 발산(수치 폭주)으로 시뮬레이션을 중단했습니다.** "
                       "변위가 물리적으로 의미 없는 수준(30cm 이상)까지 커졌습니다. "
                       "통신 지연을 줄이거나, 위상 리드 보상기를 켜거나, 게인(Kv)을 낮춰보세요.")
    else:
        half = len(hist["H"])//2
        if half > 2 and np.mean(hist["H"][half:]) > np.mean(hist["H"][:half])*1.2:
            warn_ph.warning("⚠️ 발산 경고: 통신 지연으로 인해 에너지가 증가 추세입니다. "
                             "위상 리드 보상기를 켜보세요.")
        else:
            warn_ph.success("✅ 시뮬레이션 완료! (dH/dt ≤ 0 안정 조건 만족)")
else:
    st.info("왼쪽에서 파라미터를 설정한 뒤, 위의 버튼을 눌러주세요.")

# =========================================================
# 종합 비교: 제어 OFF / 지연+보상 OFF / 지연+보상 ON
# =========================================================
st.divider()
st.subheader("⚖️ 종합 비교: 제어 OFF / 지연 + 보상 OFF / 지연 + 보상 ON")
st.caption(
    f"현재 설정된 통신 지연({delay_ms}ms)을 그대로 사용해 3가지 시나리오를 자동 실행합니다. "
    "사이드바의 '위상 리드 보상기' 체크박스는 이 비교에서는 무시되고, 두 경우(OFF/ON)를 모두 테스트합니다."
)

compare_btn = st.button("⚖️ 지연·보상기 효과 비교 실행", use_container_width=True)
compare_ph = st.empty()
compare_energy_ph = st.empty()
compare_metric_ph = st.empty()

def collect_safe(gen):
    t_list, z_list, h_list = [], [], []
    exploded = False
    for s in gen:
        t_list.append(s["t"])
        z_list.append(s["z"])
        h_list.append(s["H"])
        if s.get("exploded", False):
            exploded = True
            break
    return np.array(t_list), np.array(z_list), np.array(h_list), exploded

if compare_btn:
    t1, z1, h1, exp1 = collect_safe(run_generator(
        False, notch_on, delay_ms, False,
        impulse_amp, ambient_amp, m, k, c_damp, Kv, sim_seconds))

    t2, z2, h2, exp2 = collect_safe(run_generator(
        True, notch_on, delay_ms, False,
        impulse_amp, ambient_amp, m, k, c_damp, Kv, sim_seconds))

    t3, z3, h3, exp3 = collect_safe(run_generator(
        True, notch_on, delay_ms, True,
        impulse_amp, ambient_amp, m, k, c_damp, Kv, sim_seconds))

    z1_mm, z2_mm, z3_mm = z1*1000, z2*1000, z3*1000

    rms1 = np.sqrt(np.mean(z1_mm**2)) if len(z1_mm) else 0.0
    rms2 = np.sqrt(np.mean(z2_mm**2)) if len(z2_mm) else 0.0
    rms3 = np.sqrt(np.mean(z3_mm**2)) if len(z3_mm) else 0.0

    fig_cmp = go.Figure()
    fig_cmp.add_trace(go.Scatter(x=t1, y=z1_mm, line=dict(color='gray', dash='dot'),
                                  name='① 제어 OFF'))
    fig_cmp.add_trace(go.Scatter(x=t2, y=z2_mm, line=dict(color='red'),
                                  name='② 지연 + 보상 OFF'))
    fig_cmp.add_trace(go.Scatter(x=t3, y=z3_mm, line=dict(color='blue'),
                                  name='③ 지연 + 보상 ON'))
    fig_cmp.update_layout(title="변위 비교: OFF vs 지연(보상OFF) vs 지연(보상ON)",
                           height=420, xaxis_title="시간(s)", yaxis_title="변위(mm)",
                           legend=dict(orientation="h"))
    # ★ [점검#3] 고정 key 부여
    compare_ph.plotly_chart(fig_cmp, use_container_width=True, key="compare_displacement_chart")

    fig_energy = go.Figure()
    fig_energy.add_trace(go.Scatter(x=t1, y=h1, line=dict(color='gray', dash='dot'),
                                     name='① 제어 OFF'))
    fig_energy.add_trace(go.Scatter(x=t2, y=h2, line=dict(color='red'),
                                     name='② 지연 + 보상 OFF'))
    fig_energy.add_trace(go.Scatter(x=t3, y=h3, line=dict(color='blue'),
                                     name='③ 지연 + 보상 ON'))
    fig_energy.update_layout(title="에너지(해밀토니안) 비교 — dH/dt ≤ 0 안정 조건 확인용",
                              height=380, xaxis_title="시간(s)", yaxis_title="에너지 H",
                              legend=dict(orientation="h"))
    # ★ [점검#4] 고정 key 부여
    compare_energy_ph.plotly_chart(fig_energy, use_container_width=True, key="compare_energy_chart")

    reduction_vs_off = (rms1 - rms2) / rms1 * 100 if rms1 > 0 else 0.0
    comp_effect = (rms2 - rms3) / rms2 * 100 if rms2 > 0 else 0.0

    msg = (
        f"**① 제어 OFF RMS:** {rms1:.3f} mm&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"**② 지연+보상OFF RMS:** {rms2:.3f} mm {'💥(발산 중단)' if exp2 else ''}&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"**③ 지연+보상ON RMS:** {rms3:.3f} mm {'💥(발산 중단)' if exp3 else ''}\n\n"
        f"**📉 보상기 효과 (②→③ 감소율): {comp_effect:.1f}%**"
    )
    compare_metric_ph.markdown(msg)

    if exp2 and not exp3:
        st.success("✅ 동일한 통신 지연 조건에서, 위상 리드 보상기를 켜자 시스템 발산이 해소되었습니다!")
    elif exp2 and exp3:
        st.warning("⚠️ 현재 지연(ms)이 보상기로도 감당하지 못할 만큼 큽니다. 지연을 줄이거나 Kv를 낮춰보세요.")
    elif not exp2 and comp_effect > 0:
        st.info(f"ℹ️ 두 경우 모두 발산하지 않았지만, 보상기를 켰을 때 진동이 {comp_effect:.1f}% 더 줄었습니다.")
