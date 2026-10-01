import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

import * as relations from "./drizzle/relations";
import * as schema from "./drizzle/schema";

// Reuse one pool across hot reloads in development.
const globalForDb = globalThis as unknown as { pgPool?: Pool };

const pool =
  globalForDb.pgPool ??
  new Pool({ connectionString: process.env.DATABASE_URL });
if (process.env.NODE_ENV !== "production") globalForDb.pgPool = pool;

export const db = drizzle(pool, { schema: { ...schema, ...relations } });
export { schema };
