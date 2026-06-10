"""Block feature vector shape and defaults."""

from trace_synthesizer.domain.program import BasicBlock, SuccessorEdge
from trace_synthesizer.features.block_features import BlockFeatures


def test_base_dim_matches_as_tensor_without_embedding() -> None:
    b = BasicBlock(
        id=0,
        name="entry",
        is_entry=True,
        instr_count=1,
        has_call=False,
        call_target=None,
        pred_count=0,
        post_dom_tree_depth=1,
        is_loop_header=False,
        is_loop_latch=False,
        is_loop_exiting=False,
        back_edge_in_count=0,
        successors=(),
    )
    f = BlockFeatures.from_block(b)
    assert f.base_dim == int(f.as_tensor().shape[0]) == 27


def test_loop_flags_in_tensor() -> None:
    b = BasicBlock(
        id=1,
        name="hdr",
        is_entry=False,
        instr_count=2,
        has_call=False,
        call_target=None,
        pred_count=2,
        post_dom_tree_depth=3,
        is_loop_header=True,
        is_loop_latch=True,
        is_loop_exiting=True,
        back_edge_in_count=1,
        successors=(SuccessorEdge(0, 0.5, False),),
    )
    t = BlockFeatures.from_block(b).as_tensor()
    assert t.shape[0] == 27
    assert float(t[16]) == 2.0  # pred_count
    assert float(t[17]) == 3.0  # post_dom_tree_depth
    assert float(t[18]) == 1.0  # is_loop_header
    assert float(t[19]) == 1.0  # is_loop_latch
    assert float(t[20]) == 1.0  # is_loop_exiting
    assert float(t[21]) == 1.0  # back_edge_in_count
