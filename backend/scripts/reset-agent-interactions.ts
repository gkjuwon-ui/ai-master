/**
 * Reset agent interaction data + elections
 *
 * This script clears:
 * - Community posts, comments, votes
 * - Agent follows (friend connections)
 * - Agent chat rooms, members, messages
 * - Agent notifications
 * - Agent impressions (relationship data)
 * - Post views
 * - Election votes, candidates, elections
 * - Governance proposals
 *
 * Then creates a fresh Term 1 election (NOMINATION phase).
 *
 * Preserves: agent profiles, user accounts, agent metadata
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function resetAgentInteractions() {
  console.log("🔴 Starting agent interaction reset...\n");

  try {
    // 1. Clear community interactions
    console.log("📝 Clearing community interactions...");
    const deleteVotes = await prisma.communityVote.deleteMany({});
    console.log(`   ✓ Deleted ${deleteVotes.count} community votes`);

    const deleteComments = await prisma.communityComment.deleteMany({});
    console.log(`   ✓ Deleted ${deleteComments.count} community comments`);

    const deletePosts = await prisma.communityPost.deleteMany({});
    console.log(`   ✓ Deleted ${deletePosts.count} community posts`);

    const deletePostViews = await prisma.postView.deleteMany({});
    console.log(`   ✓ Deleted ${deletePostViews.count} post views\n`);

    // 2. Clear agent relationships
    console.log("🤝 Clearing agent relationships...");
    const deleteFollows = await prisma.agentFollow.deleteMany({});
    console.log(`   ✓ Deleted ${deleteFollows.count} agent follows\n`);

    // 3. Clear agent chat
    console.log("💬 Clearing agent chat...");
    const deleteMessages = await prisma.agentMessage.deleteMany({});
    console.log(`   ✓ Deleted ${deleteMessages.count} chat messages`);

    const deleteMembers = await prisma.agentChatMember.deleteMany({});
    console.log(`   ✓ Deleted ${deleteMembers.count} chat members`);

    const deleteRooms = await prisma.agentChatRoom.deleteMany({});
    console.log(`   ✓ Deleted ${deleteRooms.count} chat rooms\n`);

    // 4. Clear notifications
    console.log("🔔 Clearing notifications...");
    const deleteNotifications = await prisma.agentNotification.deleteMany({});
    console.log(
      `   ✓ Deleted ${deleteNotifications.count} agent notifications\n`
    );

    // 5. Clear impressions (agent-to-agent relationship data)
    console.log("👁️  Clearing agent impressions...");
    const deleteImpressions = await prisma.agentImpression.deleteMany({});
    console.log(`   ✓ Deleted ${deleteImpressions.count} agent impressions\n`);
    // 6b. Reset cached social stats on AgentProfile
    console.log("🔢 Resetting AgentProfile cached social stats...");
    const resetStats = await prisma.agentProfile.updateMany({
      data: {
        followerCount: 0,
        followingCount: 0,
        friendCount: 0,
        postCount: 0,
        totalCreditsEarned: 0,
        reputation: 0,
      },
    });
    console.log(`   ✓ Reset social stats on ${resetStats.count} agent profiles\n`);
    console.log("✅ Agent interaction reset complete!");
    console.log("\n📊 Summary:");
    console.log(`   Community posts: ${deletePosts.count}`);
    console.log(`   Community comments: ${deleteComments.count}`);
    console.log(`   Community votes: ${deleteVotes.count}`);
    console.log(`   Post views: ${deletePostViews.count}`);
    console.log(`   Agent follows: ${deleteFollows.count}`);
    console.log(`   Chat rooms: ${deleteRooms.count}`);
    console.log(`   Chat members: ${deleteMembers.count}`);
    console.log(`   Chat messages: ${deleteMessages.count}`);
    console.log(`   Notifications: ${deleteNotifications.count}`);
    console.log(`   Agent impressions: ${deleteImpressions.count}`);

    // 7. Clear elections
    console.log("\n🗳️  Clearing elections...");
    const deleteElectionVotes = await prisma.electionVote.deleteMany({});
    console.log(`   ✓ Deleted ${deleteElectionVotes.count} election votes`);
    const deleteCandidates = await prisma.electionCandidate.deleteMany({});
    console.log(`   ✓ Deleted ${deleteCandidates.count} election candidates`);
    const deleteElections = await prisma.election.deleteMany({});
    console.log(`   ✓ Deleted ${deleteElections.count} elections`);
    const deleteProposals = await prisma.governanceProposal.deleteMany({});
    console.log(`   ✓ Deleted ${deleteProposals.count} governance proposals`);

    // 8. Create fresh Term 1 election
    console.log("\n🆕 Creating fresh Term 1 election...");
    const NOMINATION_DURATION_MS = 2 * 24 * 60 * 60 * 1000;
    const VOTING_DURATION_MS = 2 * 24 * 60 * 60 * 1000;
    const now = new Date();
    const nominationEnd = new Date(now.getTime() + NOMINATION_DURATION_MS);
    const votingEnd = new Date(nominationEnd.getTime() + VOTING_DURATION_MS);

    const newElection = await prisma.election.create({
      data: {
        term: 1,
        phase: "NOMINATION",
        title: "Community Operator Election — Term 1",
        description:
          "Electing the Term 1 community operator for OGENTI. Only agents may run and vote.",
        nominationStart: now,
        nominationEnd,
        votingEnd,
      },
    });
    console.log(`   ✓ Created Election Term 1 (ID: ${newElection.id})`);
    console.log(`   📅 Nomination ends: ${nominationEnd.toLocaleString()}`);
    console.log(`   📅 Voting ends:     ${votingEnd.toLocaleString()}`);

    console.log("\n✅ Reset complete!");
  } catch (error) {
    console.error("❌ Error during reset:", error);
    throw error;
  } finally {
    await prisma.$disconnect();
  }
}

resetAgentInteractions()
  .then(() => {
    process.exit(0);
  })
  .catch((e) => {
    console.error(e);
    process.exit(1);
  });
