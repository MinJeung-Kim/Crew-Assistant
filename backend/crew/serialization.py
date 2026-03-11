from .models import CrewFlowGraph


def crew_graph_to_dict(graph: CrewFlowGraph) -> dict[str, object]:
    return {
        "topic": graph.topic,
        "target_year": graph.target_year,
        "agents": [
            {
                "id": agent.id,
                "role": agent.role,
                "goal": agent.goal,
            }
            for agent in graph.agents
        ],
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "agent_id": task.agent_id,
                "depends_on": list(task.depends_on),
                "description": task.description,
                "expected_output": task.expected_output,
            }
            for task in graph.tasks
        ],
    }
