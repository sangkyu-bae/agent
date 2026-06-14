import {
  Chart,
  // controllers
  BarController,
  LineController,
  PieController,
  DoughnutController,
  ScatterController,
  RadarController,
  // elements
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  // scales
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  // plugins
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';

let registered = false;

/**
 * chart.js 컴포넌트를 1회만 등록한다 (tree-shaking 통제).
 * useChart 내부에서 호출하여 인스턴스 생성 전 등록을 보장한다.
 *
 * Design: docs/02-design/features/chat-chart-rendering.design.md §11.2 Step 4
 */
export const ensureChartRegistered = (): void => {
  if (registered) return;
  Chart.register(
    BarController,
    LineController,
    PieController,
    DoughnutController,
    ScatterController,
    RadarController,
    BarElement,
    LineElement,
    PointElement,
    ArcElement,
    CategoryScale,
    LinearScale,
    RadialLinearScale,
    Title,
    Tooltip,
    Legend,
    Filler,
  );
  registered = true;
};
