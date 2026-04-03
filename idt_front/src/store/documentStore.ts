import { create } from 'zustand';
import type { Document } from '@/types/rag';
import {
  createLoadingSlice,
  createListSlice,
  createSelectionSlice,
  type LoadingSlice,
  type ListSlice,
  type SelectionSlice,
} from './commonSlices';

type DocumentState = LoadingSlice & ListSlice<Document> & SelectionSlice;

export const useDocumentStore = create<DocumentState>()((...args) => ({
  ...createLoadingSlice<DocumentState>()(...args),
  ...createListSlice<Document, DocumentState>()(...args),
  ...createSelectionSlice<DocumentState>()(...args),
}));
