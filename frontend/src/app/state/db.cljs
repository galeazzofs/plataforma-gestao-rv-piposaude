(ns app.state.db)

(def initial-db
  {:auth {:user nil            ;; {:id, :email, :name, :role, :team_id}
          :access-token nil
          :refresh-token nil
          :loading? false
          :error nil}

   :notifications {:items []
                   :unread-count 0
                   :loading? false}

   :ui {:sidebar-collapsed? false
        :active-modal nil
        :toast nil}

   ;; Page-specific data loaded on demand
   :policies {:items []
              :meta nil
              :loading? false
              :filters {:quarter nil :year nil :status nil}}

   :commissions {:items []
                 :summary nil
                 :projection []
                 :loading? false}

   :goals {:items []
           :loading? false}

   :appraisal {:current nil    ;; Active appraisal being worked on
               :list []
               :loading? false}

   :validations {:items []
                 :loading? false}

   :finance {:dashboard nil
             :loading? false
             :dashboard-error nil
             :dashboard-request-id nil}

   :admin {:users []
           :teams []
           :commission-table {:current-version nil :rows []}
           :settings nil
           :sync-status nil
           :audit-log {:items [] :meta nil}}})
