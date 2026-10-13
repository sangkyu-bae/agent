import { beforeEach, describe, expect, it } from 'vitest';
import { useExcelPreviewStore } from './excelPreviewStore';

// excel-preview Design §8.3 #13 — open/close 상태 전이
describe('excelPreviewStore', () => {
  beforeEach(() => {
    useExcelPreviewStore.setState({ target: null });
  });

  it('초기 상태는 닫힘(target=null)이다', () => {
    expect(useExcelPreviewStore.getState().target).toBeNull();
  });

  it('open은 target을 설정한다', () => {
    useExcelPreviewStore.getState().open({ fileId: 'a'.repeat(32), filename: '매출.xlsx' });
    expect(useExcelPreviewStore.getState().target).toEqual({
      fileId: 'a'.repeat(32),
      filename: '매출.xlsx',
    });
  });

  it('close는 target을 해제한다', () => {
    useExcelPreviewStore.getState().open({ fileId: 'b'.repeat(32), filename: 'x.xlsx' });
    useExcelPreviewStore.getState().close();
    expect(useExcelPreviewStore.getState().target).toBeNull();
  });

  it('open을 연속 호출하면 마지막 target으로 교체된다', () => {
    useExcelPreviewStore.getState().open({ fileId: 'a'.repeat(32), filename: '1.xlsx' });
    useExcelPreviewStore.getState().open({ fileId: 'b'.repeat(32), filename: '2.xlsx' });
    expect(useExcelPreviewStore.getState().target?.filename).toBe('2.xlsx');
  });
});
