components {
  id: "mesh"
  component: "/main/platforms/burning/platform.mesh"
}
components {
  id: "mesh_default"
  component: "/main/platforms/default/platform.mesh"
}
components {
  id: "collision_object"
  component: "/main/platforms/platform.collisionobject"
}
components {
  id: "bend"
  component: "/main/platforms/platform.script"
}
components {
  id: "burning"
  component: "/main/platforms/burning/burning.script"
  properties {
    id: "burning"
    value: "1.0"
    type: PROPERTY_TYPE_NUMBER
  }
}
components {
  id: "slope"
  component: "/main/platforms/sloped/sloped.script"
  properties {
    id: "direction"
    value: "0.0"
    type: PROPERTY_TYPE_NUMBER
  }
}
