"""streamlit run frontend/replay_app.py; uploads only, no live state writes."""
def main():
    import streamlit as st
    from rail_crane_scheduler.contracts import ContractError
    from rail_crane_scheduler.replay import load_replay,compare,gantt_figure,rail_figure,png_bytes
    st.set_page_config(page_title='Project04 Crane Replay',layout='wide')
    st.title('Quay crane schedule replay')
    st.caption('Read-only source records. Fixture playback is not scientific performance evidence.')
    problem=st.file_uploader('Problem JSON',type=['json'])
    schedules=st.file_uploader('Recorded schedules or run records',type=['json'],accept_multiple_files=True)
    if not problem or not schedules:
        st.info('Upload an existing problem and one or more recorded schedules. This page never schedules or trains.')
        return
    try:
        replays=[load_replay(problem.getvalue(),s.getvalue()) for s in schedules]
        st.dataframe(compare(replays),use_container_width=True)
        selected=st.selectbox('Policy trace',range(len(replays)),format_func=lambda i:replays[i].schedule.policy_id)
        replay=replays[selected]
        st.write('Provenance',replay.problem.metadata.to_dict())
        if replay.problem.metadata.origin=='TEST_FIXTURE_SYNTHETIC': st.warning('TEST FIXTURE ONLY — no calibrated or held-out performance claim.')
        if not replay.verdict.valid_complete: st.error('Incomplete or rejected plan: '+', '.join(replay.verdict.errors))
        if not replay.motion_safe: return
        ids=[t.task_id for t in replay.problem.tasks]
        selected_tasks=st.multiselect('Gantt task filter',ids,default=ids)
        fig=gantt_figure(replay,set(selected_tasks)); st.pyplot(fig)
        start=replay.problem.vessel.planning_start_min; stop=replay.schedule.stop_min
        time=st.slider('Playback time (simulation min)',min_value=float(start),max_value=float(stop),value=float(start)) if stop>start else start
        st.pyplot(rail_figure(replay,time))
        st.download_button('Export displayed Gantt PNG',png_bytes(fig),'crane_gantt.png','image/png')
        st.write('Unfinished original jobs',[t.task_id for t in replay.problem.tasks if t.task_id not in replay.verdict.completed_task_ids])
    except (ContractError,ValueError,KeyError) as exc:
        st.error(str(exc))


if __name__=='__main__': main()
