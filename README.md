\# 가상 능동 진동 저감 시뮬레이터 (PBC + 노치필터 + 지연보상)



실제 하드웨어 없이, 물리 모델로 책상 진동/기구 공진/통신 지연까지 전부 가상으로 재현한

해밀토니안 수동성 제어(Passivity-Based Control) 기반 능동 진동 저감 시뮬레이터입니다.



\## 🔗 라이브 데모

👉 **[여기를 클릭해서 바로 체험하기](https://virtual-vibration-sim.streamlit.app)**



\## 📌 주요 기능

\- 책상 흔들림을 질량-스프링-댐퍼 모델로 시뮬레이션

\- 해밀토니안 에너지 셰이핑 기반 PBC(Passivity-Based Control) 제어기

\- 13.5Hz 기구 공진을 제거하는 디지털 IIR 노치 필터

\- 통신 지연(Latency)을 보상하는 위상 리드(Lead) 보상기

\- (z, p) 위상 공간 궤적 및 해밀토니안 에너지 실시간 시각화

\- 제어 OFF / 지연+보상 OFF / 지연+보상 ON 3가지 시나리오 종합 비교



\## 🧪 실험 결과 요약



| 시나리오 | 통신지연 | 제어게인(Kv) | 보상기 | RMS 변위 | 결과 |

|---|---|---|---|---|---|

| 발산 케이스 | 35ms | 15 | OFF | 76.4mm | 발산 |

| 보상 역부족 | 35ms | 15 | ON | 66.8mm | 여전히 발산 |

| 지연 완화 | 20ms | 15 | ON | 2.8mm | 안정 |

| 게인 조정 성공 | 35ms | 8 | ON | 3.6mm | 96.4% 개선 |



\## 🖥️ 로컬 실행 방법



pip install -r requirements.txt

streamlit run app.py



\## 📸 스크린샷

스크린샷은 screenshots 폴더를 참고하세요.



\## 🛠️ 기술 스택

Python, Streamlit, NumPy, Plotly, 해석역학(Hamiltonian Mechanics)

