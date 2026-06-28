from src.diff import compute_diff

def test_first_run():
    curr = {"followers": ["a"], "following": ["b"]}
    res = compute_diff(curr, None)
    assert res.is_first_run

def test_diff_logic():
    prev = {
        "followers": ["user1", "user2", "user3"],
        "following": ["user1", "user2", "user4"]
    }
    curr = {
        "followers": ["user1", "user3", "user_new"],
        "following": ["user1", "user_new2"]
    }
    
    # Unfollowers: user2 left followers
    # New followers: user_new
    # Not following back: curr_following - curr_followers -> user1(both) -> user_new2
    # Suspicious deactivations: user2 was in both prev_followers and prev_following, now in neither!
    
    res = compute_diff(curr, prev)
    
    assert not res.is_first_run
    assert "user_new" in res.new_followers
    assert "user_new2" in res.not_following_back
    assert "user2" in res.suspicious_deactivations
    assert "user2" not in res.unfollowers # Should not double-count
