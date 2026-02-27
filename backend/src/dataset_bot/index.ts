import { startDatasetBot } from './discord_bot';

startDatasetBot().catch((e) => {
  console.error(e);
  process.exit(1);
});
