import type { NodeTypes } from '@xyflow/react';
import AgentNode from './AgentNode';
import ResourceNode from './ResourceNode';

export const nodeTypes: NodeTypes = {
  agent: AgentNode,
  resource: ResourceNode,
};
