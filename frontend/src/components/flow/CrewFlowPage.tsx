import { useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { CrewGraph, CrewProgress, CrewTaskStatus } from "../../types/chat";
import { IconMenu } from "../icons";
import styles from "./CrewFlowPage.module.css";

interface CrewFlowPageProps {
  crewGraph: CrewGraph | null;
  crewProgress: CrewProgress | null;
  onToggleSidebar: () => void;
}

const TOPIC_MAX_CHARS = 72;
const TASK_STATUS_LABEL: Record<CrewTaskStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

function getShortTopic(topic: string): string {
  let normalized = topic.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "(no topic)";
  }

  const cutoffMarkers = [
    "Use the following company knowledge as grounded context.",
    "[Source ",
  ];

  for (const marker of cutoffMarkers) {
    const markerIndex = normalized.indexOf(marker);
    if (markerIndex > -1) {
      normalized = normalized.slice(0, markerIndex).trim();
    }
  }

  if (normalized.length <= TOPIC_MAX_CHARS) {
    return normalized;
  }

  return `${normalized.slice(0, TOPIC_MAX_CHARS - 3).trimEnd()}...`;
}

function getTaskStatusMap(progress: CrewProgress | null): Map<string, CrewTaskStatus> {
  if (!progress) {
    return new Map();
  }

  return new Map(progress.tasks.map((task) => [task.task_id, task.status]));
}

function getTaskNodeStyle(status: CrewTaskStatus): Node["style"] {
  if (status === "running") {
    return {
      width: 320,
      border: "2px solid #3b82f6",
      borderRadius: "14px",
      background: "#eff6ff",
      boxShadow: "0 12px 26px rgba(59, 130, 246, 0.2)",
      padding: "0",
    };
  }

  if (status === "completed") {
    return {
      width: 320,
      border: "1px solid #86efac",
      borderRadius: "14px",
      background: "#f0fdf4",
      boxShadow: "0 8px 18px rgba(34, 197, 94, 0.12)",
      padding: "0",
    };
  }

  if (status === "failed") {
    return {
      width: 320,
      border: "1px solid #fda4af",
      borderRadius: "14px",
      background: "#fff1f2",
      boxShadow: "0 8px 18px rgba(244, 63, 94, 0.12)",
      padding: "0",
    };
  }

  return {
    width: 320,
    border: "1px solid #d0d7de",
    borderRadius: "14px",
    background: "#ffffff",
    boxShadow: "0 8px 18px rgba(15, 23, 42, 0.08)",
    padding: "0",
  };
}

function getAgentNodeStyle(isActive: boolean): Node["style"] {
  if (isActive) {
    return {
      width: 270,
      border: "2px solid #3b82f6",
      borderRadius: "14px",
      background: "#eff6ff",
      boxShadow: "0 10px 22px rgba(59, 130, 246, 0.18)",
      padding: "0",
    };
  }

  return {
    width: 270,
    border: "1px solid #fecaca",
    borderRadius: "14px",
    background: "#fff8f8",
    boxShadow: "0 8px 20px rgba(239, 68, 68, 0.09)",
    padding: "0",
  };
}

function buildGraph(
  crewGraph: CrewGraph,
  taskStatusMap: Map<string, CrewTaskStatus>,
  activeAgentId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const statusClassMap: Record<CrewTaskStatus, string> = {
    pending: styles.nodeStatePending,
    running: styles.nodeStateRunning,
    completed: styles.nodeStateCompleted,
    failed: styles.nodeStateFailed,
  };

  crewGraph.agents.forEach((agent, index) => {
    const isActiveAgent = activeAgentId === agent.id;
    nodes.push({
      id: `agent:${agent.id}`,
      position: { x: 40, y: 56 + index * 136 },
      data: {
        label: (
          <div className={styles.agentNode}>
            <div className={styles.nodeHeader}>
              <div className={styles.nodeBadge}>AGENT</div>
              {isActiveAgent && <span className={styles.nodeStateAgent}>Active</span>}
            </div>
            <div className={styles.nodeTitle}>{agent.role}</div>
            <div className={styles.nodeText}>{agent.goal}</div>
          </div>
        ),
      },
      style: getAgentNodeStyle(isActiveAgent),
    });
  });

  crewGraph.tasks.forEach((task, index) => {
    const taskStatus = taskStatusMap.get(task.id) ?? "pending";
    const taskDescription = task.description?.trim() || "Task detail is not available.";

    nodes.push({
      id: `task:${task.id}`,
      position: { x: 420, y: 56 + index * 136 },
      data: {
        label: (
          <div className={styles.taskNode}>
            <div className={styles.nodeHeader}>
              <div className={styles.nodeBadgeTask}>TASK</div>
              <span className={`${styles.nodeState} ${statusClassMap[taskStatus]}`}>
                {TASK_STATUS_LABEL[taskStatus]}
              </span>
            </div>
            <div className={styles.nodeTitle}>{task.title}</div>
            <div className={styles.nodeText}>Owner: {task.agent_id}</div>
            <div className={styles.nodeText}>{taskDescription}</div>
          </div>
        ),
      },
      style: getTaskNodeStyle(taskStatus),
    });

    edges.push({
      id: `assign:${task.agent_id}:${task.id}`,
      source: `agent:${task.agent_id}`,
      target: `task:${task.id}`,
      type: "smoothstep",
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#ef4444",
      },
      style: {
        stroke: "#ef4444",
        strokeWidth: 1.9,
      },
      label: "assign",
      labelStyle: {
        fill: "#ef4444",
        fontSize: 11,
        fontWeight: 700,
      },
    });

    task.depends_on.forEach((depId) => {
      edges.push({
        id: `depends:${depId}:${task.id}`,
        source: `task:${depId}`,
        target: `task:${task.id}`,
        type: "step",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "#64748b",
        },
        style: {
          stroke: "#64748b",
          strokeWidth: 1.6,
          strokeDasharray: "5 4",
        },
        label: "depends",
        labelStyle: {
          fill: "#64748b",
          fontSize: 10,
          fontWeight: 700,
        },
      });
    });
  });

  return { nodes, edges };
}

export function CrewFlowPage({ crewGraph, crewProgress, onToggleSidebar }: CrewFlowPageProps) {
  const taskStatusMap = useMemo(() => getTaskStatusMap(crewProgress), [crewProgress]);

  const graphElements = useMemo(() => {
    if (!crewGraph) {
      return { nodes: [], edges: [] };
    }
    return buildGraph(crewGraph, taskStatusMap, crewProgress?.active_agent_id ?? null);
  }, [crewGraph, taskStatusMap, crewProgress?.active_agent_id]);

  const [nodes, setNodes, onNodesChange] = useNodesState(graphElements.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(graphElements.edges);

  useEffect(() => {
    setNodes((prevNodes) => {
      const previousPositions = new Map(prevNodes.map((node) => [node.id, node.position]));
      return graphElements.nodes.map((node) => ({
        ...node,
        position: previousPositions.get(node.id) ?? node.position,
      }));
    });
    setEdges(graphElements.edges);
  }, [graphElements.edges, graphElements.nodes, setEdges, setNodes]);

  const shortTopic = useMemo(() => {
    if (!crewGraph) {
      return "";
    }
    return getShortTopic(crewGraph.topic);
  }, [crewGraph]);

  const activeTask = useMemo(() => {
    if (!crewGraph || !crewProgress?.active_task_id) {
      return null;
    }
    return crewGraph.tasks.find((task) => task.id === crewProgress.active_task_id) ?? null;
  }, [crewGraph, crewProgress?.active_task_id]);

  const activeAgentRole = useMemo(() => {
    if (!crewGraph || !crewProgress?.active_agent_id) {
      return null;
    }
    return (
      crewGraph.agents.find((agent) => agent.id === crewProgress.active_agent_id)?.role
      ?? crewProgress.active_agent_id
    );
  }, [crewGraph, crewProgress?.active_agent_id]);

  const runningLabel = activeTask && activeAgentRole
    ? `${activeAgentRole} - ${activeTask.title}`
    : "Idle";

  const detailStatusClassMap: Record<CrewTaskStatus, string> = {
    pending: styles.taskCardPending,
    running: styles.taskCardRunning,
    completed: styles.taskCardCompleted,
    failed: styles.taskCardFailed,
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button type="button" onClick={onToggleSidebar} className={styles.menuButton}>
          <IconMenu />
        </button>
        <div>
          <div className={styles.title}>CrewAI Agent-Task Flow</div>
          <div className={styles.subtitle}>
            CrewAI가 자동 구성한 에이전트와 태스크 연결 관계를 시각화합니다.
          </div>
        </div>
      </div>

      {crewGraph ? (
        <div className={styles.meta}>
          <div>
            <span className={styles.metaLabel}>Topic</span>
            <span className={`${styles.metaValue} ${styles.metaTopic}`} title={crewGraph.topic}>
              {shortTopic}
            </span>
          </div>
          <div>
            <span className={styles.metaLabel}>Year</span>
            <span className={styles.metaValue}>{crewGraph.target_year}</span>
          </div>
          <div>
            <span className={styles.metaLabel}>Agents</span>
            <span className={styles.metaValue}>{crewGraph.agents.length}</span>
          </div>
          <div>
            <span className={styles.metaLabel}>Tasks</span>
            <span className={styles.metaValue}>{crewGraph.tasks.length}</span>
          </div>
          <div>
            <span className={styles.metaLabel}>Running</span>
            <span className={`${styles.metaValue} ${styles.metaRunning}`} title={runningLabel}>
              {runningLabel}
            </span>
          </div>
        </div>
      ) : (
        <div className={styles.emptyState}>
          채팅에서 CrewAI 요청을 실행하면 그래프가 표시됩니다.
        </div>
      )}

      {crewGraph && (
        <div className={styles.taskDetailsPanel}>
          {crewGraph.tasks.map((task) => {
            const taskStatus = taskStatusMap.get(task.id) ?? "pending";
            const ownerRole =
              crewGraph.agents.find((agent) => agent.id === task.agent_id)?.role
              ?? task.agent_id;

            return (
              <article
                key={task.id}
                className={`${styles.taskDetailCard} ${detailStatusClassMap[taskStatus]}`}
              >
                <div className={styles.taskDetailHeader}>
                  <h4 className={styles.taskDetailTitle}>{task.title}</h4>
                  <span className={`${styles.taskStatusPill} ${styles[`taskStatus${TASK_STATUS_LABEL[taskStatus]}`]}`}>
                    {TASK_STATUS_LABEL[taskStatus]}
                  </span>
                </div>
                <div className={styles.taskDetailMeta}>Agent: {ownerRole}</div>
                <p className={styles.taskDetailText}>
                  {task.description?.trim() || "Task description is not available."}
                </p>
                <p className={styles.taskDetailOutput}>
                  Expected Output: {task.expected_output?.trim() || "N/A"}
                </p>
              </article>
            );
          })}
        </div>
      )}

      <div className={styles.canvas}>
        {crewGraph ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodesDraggable
            nodesConnectable={false}
            fitView
            minZoom={0.45}
            maxZoom={1.8}
            fitViewOptions={{ padding: 0.24 }}
            proOptions={{ hideAttribution: true }}
          >
            <MiniMap
              pannable
              zoomable
              style={{
                background: "#f8fafc",
                border: "1px solid #dbe3ee",
                borderRadius: 8,
              }}
            />
            <Controls />
            <Background gap={18} color="#e5e7eb" />
          </ReactFlow>
        ) : (
          <div className={styles.canvasPlaceholder}>Crew graph is not available yet.</div>
        )}
      </div>
    </div>
  );
}
