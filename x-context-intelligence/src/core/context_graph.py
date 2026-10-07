from __future__ import annotations

from typing import Any, Dict, List
from src.models.types import ContextGraph, QuoteNode, ReplyNode, RootPost


class ContextGraphBuilder:
    """
    Constructs a provenance-preserving graph of all entities in the X context:
    Nodes: ROOT_POST, AUTHOR, MEDIA, REPLY, QUOTE, LINK
    Edges: AUTHORED, CONTAINS_MEDIA, REPLIED_TO, FOLLOWS_UP, QUOTED, LINKS_TO
    """

    def build_graph(
        self,
        root: RootPost,
        author_followups: List[ReplyNode],
        replies: List[ReplyNode],
        quotes: List[QuoteNode],
    ) -> ContextGraph:
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        seen_node_ids = set()

        def add_node(node_id: str, label: str, node_type: str, props: Dict[str, Any]):
            if node_id not in seen_node_ids:
                seen_node_ids.add(node_id)
                nodes.append({
                    "id": node_id,
                    "label": label,
                    "type": node_type,
                    "properties": props
                })

        def add_edge(source: str, target: str, relation: str, props: Dict[str, Any] = None):
            edges.append({
                "source": source,
                "target": target,
                "relation": relation,
                "properties": props or {}
            })

        # 1. Author Node
        author_node_id = f"author_{root.author.handle or 'unknown'}"
        add_node(
            author_node_id,
            f"@{root.author.handle} ({root.author.name})",
            "AUTHOR",
            {"name": root.author.name, "handle": root.author.handle, "verified": root.author.verified}
        )

        # 2. Root Post Node
        root_node_id = f"post_{root.id}"
        add_node(
            root_node_id,
            f"Root Post {root.id}",
            "ROOT_POST",
            {
                "url": root.url,
                "text": root.text[:120] + ("..." if len(root.text) > 120 else ""),
                "likes": root.likes,
                "retweets": root.retweets,
                "replies_count": root.replies_count
            }
        )
        add_edge(author_node_id, root_node_id, "AUTHORED")

        # 3. Media Nodes for Root
        for idx, m in enumerate(root.media):
            m_id = f"media_{root.id}_{idx}"
            add_node(
                m_id,
                f"{m.type.upper()} ({m.width}x{m.height})" if m.width else f"{m.type.upper()}",
                "MEDIA",
                {
                    "type": m.type,
                    "url": m.url,
                    "duration": m.duration_seconds,
                    "summary": m.summary
                }
            )
            add_edge(root_node_id, m_id, "CONTAINS_MEDIA")

        # 4. Links for Root
        for idx, l in enumerate(root.links):
            l_id = f"link_{root.id}_{idx}"
            add_node(
                l_id,
                l.title or l.domain or l.url[:30],
                "LINK",
                {"url": l.url, "domain": l.domain, "resolved": l.resolved}
            )
            add_edge(root_node_id, l_id, "LINKS_TO")

        # 5. Author Follow-up Nodes
        for f in author_followups:
            f_node_id = f"reply_{f.id}"
            add_node(
                f_node_id,
                f"Author Follow-up ({f.id})",
                "AUTHOR_FOLLOWUP",
                {"text": f.text, "likes": f.likes}
            )
            add_edge(author_node_id, f_node_id, "AUTHORED")
            add_edge(f_node_id, root_node_id, "FOLLOWS_UP")

        # 6. Community Replies
        for r in replies:
            r_author_id = f"author_{r.author.handle or 'anon'}"
            add_node(
                r_author_id,
                f"@{r.author.handle}",
                "AUTHOR",
                {"name": r.author.name, "handle": r.author.handle}
            )
            r_node_id = f"reply_{r.id}"
            add_node(
                r_node_id,
                f"Reply from @{r.author.handle}",
                "REPLY",
                {
                    "text": r.text[:100],
                    "category": r.category,
                    "rank": r.rank,
                    "likes": r.likes
                }
            )
            add_edge(r_author_id, r_node_id, "AUTHORED")
            add_edge(r_node_id, root_node_id, "REPLIED_TO")

        # 7. Quotes
        for q in quotes:
            q_node_id = f"quote_{q.id}"
            add_node(
                q_node_id,
                f"Quote by @{q.author.handle}",
                "QUOTE",
                {"text": q.text[:100], "likes": q.likes}
            )
            add_edge(q_node_id, root_node_id, "QUOTED")

        return ContextGraph(nodes=nodes, edges=edges)
