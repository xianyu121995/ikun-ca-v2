import { generateTweetEvent } from "./hackathon-analysis";
import { saveTweetEvent, tweetsPendingAnalysis } from "./hackathon-watches";

/** One stored tweet per call, same pace as the tracking timeline pass. Failures are not saved. */
export async function analyzePendingHackathonTweets() {
  const pending = tweetsPendingAnalysis(1);
  for (const tweet of pending) {
    const result = await generateTweetEvent({
      text: tweet.text,
      occurred_at: tweet.occurred_at,
      handle: tweet.handle,
      project_name: tweet.project_name,
      place: "",
    });
    if (!result.ok) continue;
    saveTweetEvent({
      watch_id: tweet.watch_id,
      tweet_id: tweet.tweet_id,
      title: result.title,
      analysis: result.analysis,
      date: result.date,
      hour: result.hour,
      status: result.status,
      starts_at: result.starts_at,
      thin: result.thin,
    });
  }
}
