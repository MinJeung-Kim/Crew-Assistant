import { useMemo } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { CrewGraph } from "../../types/chat";
import { IconMenu } from "../icons";
import styles from "./CrewFlowPage.module.css";

interface CrewFlowPageProps {
  crewGraph: CrewGraph | null;
  onToggleSidebar: () => void;
}

const TOPIC_MAX_CHARS = 72;

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

function buildGraph(crewGraph: CrewGraph): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  crewGraph.agents.forEach((agent, index) => {
    nodes.push({
      id: `agent:${agent.id}`,
      position: { x: 40, y: 56 + index * 136 },
      draggable: false,
      data: {
        label: (
          <div className={styles.agentNode}>
            <div className={styles.nodeBadge}>AGENT</div>
            <div className={styles.nodeTitle}>{agent.role}</div>
            <div className={styles.nodeText}>{agent.goal}</div>
          </div>
        ),
      },
      style: {
        width: 260,
        border: "1px solid #fecaca",
        borderRadius: "14px",
        background: "#fff8f8",
        boxShadow: "0 8px 20px rgba(239, 68, 68, 0.09)",
        padding: "0",
      },
    });
  });

  crewGraph.tasks.forEach((task, index) => {
    nodes.push({
      id: `task:${task.id}`,
      position: { x: 420, y: 56 + index * 136 },
      draggable: false,
      data: {
        label: (
          <div className={styles.taskNode}>
            <div className={styles.nodeBadgeTask}>TASK</div>
            <div className={styles.nodeTitle}>{task.title}</div>
            <div className={styles.nodeText}>Owner: {task.agent_id}</div>
          </div>
        ),
      },
      style: {
        width: 300,
        border: "1px solid #d0d7de",
        borderRadius: "14px",
        background: "#ffffff",
        boxShadow: "0 8px 18px rgba(15, 23, 42, 0.08)",
        padding: "0",
      },
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

export function CrewFlowPage({ crewGraph, onToggleSidebar }: CrewFlowPageProps) {
  const { nodes, edges } = useMemo(() => {
    if (!crewGraph) {
      return { nodes: [], edges: [] };
    }
    return buildGraph(crewGraph);
  }, [crewGraph]);

  const shortTopic = useMemo(() => {
    if (!crewGraph) {
      return "";
    }
    return getShortTopic(crewGraph.topic);
  }, [crewGraph]);

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
        </div>
      ) : (
        <div className={styles.emptyState}>
          채팅에서 CrewAI 요청을 실행하면 그래프가 표시됩니다.
        </div>
      )}

      <div className={styles.canvas}>
        {crewGraph ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
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
