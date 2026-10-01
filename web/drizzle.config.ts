import { defineConfig } from "drizzle-kit";

// The schema is owned by the dbmate SQL migrations in ../db/migrations.
// Drizzle only introspects it (`pnpm db:pull`); never generate migrations from here.
try {
  process.loadEnvFile("../.env");
} catch {
  // No repo-root .env (e.g. CI): DATABASE_URL must already be in the environment.
}

export default defineConfig({
  dialect: "postgresql",
  out: "./src/lib/drizzle",
  dbCredentials: {
    url: process.env.DATABASE_URL!,
  },
  tablesFilter: ["!schema_migrations"],
});
